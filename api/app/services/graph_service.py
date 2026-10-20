"""Neo4j-backed graph algorithms: cycles, communities, centrality, risk scoring,
entity resolution, and explainability. Each function returns plain dicts consumed
by the API layer."""

from typing import Any, Dict, List, Optional, Set, Tuple

from neo4j.time import DateTime, Date

from ..config import settings


def _node_to_dict(node: Any) -> Dict[str, Any]:
    d = dict(node)
    for k, v in list(d.items()):
        if isinstance(v, DateTime):
            d[k] = v.isoformat()
        elif isinstance(v, Date):
            d[k] = v.isoformat()
    return d


def _sanitize(value: Any) -> Any:
    if isinstance(value, (DateTime, Date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    return value


async def search_entities(session, q: str, limit: int) -> List[Dict[str, Any]]:
    query = """
    MATCH (n)
    WHERE toLower(n.name) CONTAINS toLower($q)
       OR n.cin CONTAINS $q
       OR n.gstin CONTAINS $q
       OR n.din CONTAINS $q
       OR n.ifsc CONTAINS $q
    RETURN n, labels(n) AS labels
    LIMIT $limit
    """
    result = await session.run(query, q=q, limit=limit)
    records = await result.data()
    out = []
    for r in records:
        node = r["n"]
        labels = r["labels"]
        label = labels[0] if labels else "Unknown"
        identifier = (
            node.get("cin") or node.get("gstin") or node.get("din")
            or node.get("ifsc") or node.get("normalized_address")
            or node.get("id", "")
        )
        out.append({
            "id": node.get("id", ""),
            "type": label,
            "name": node.get("name") or node.get("cin") or node.get("id", ""),
            "identifier": identifier,
            "risk_score": node.get("risk_score"),
            "status": node.get("status"),
            "state": node.get("state"),
        })
    return out


async def get_entity(session, entity_id: str) -> Optional[Dict[str, Any]]:
    query = """
    MATCH (n)
    WHERE n.id = $id
    RETURN n, labels(n) AS labels
    """
    result = await session.run(query, id=entity_id)
    record = await result.single()
    if not record:
        return None
    node = record["n"]
    data = _node_to_dict(node)
    data["_labels"] = record["labels"]
    return data


async def get_entity_by_identifier(session, identifier: str) -> Optional[Dict[str, Any]]:
    query = """
    MATCH (n)
    WHERE n.cin = $q OR n.gstin = $q OR n.id = $q
    RETURN n, labels(n) AS labels
    LIMIT 1
    """
    result = await session.run(query, q=identifier)
    record = await result.single()
    if not record:
        return None
    node = record["n"]
    data = _node_to_dict(node)
    data["_labels"] = record["labels"]
    return data


async def get_network(session, entity_id: str, hops: int) -> Dict[str, Any]:
    if not (1 <= hops <= settings.max_neighborhood_hops):
        hops = settings.default_neighborhood_hops
    query = f"""
    MATCH path = (n)-[*1..{hops}]-(m)
    WHERE n.id = $id
    RETURN nodes(path) AS nodes, [n IN nodes(path) | labels(n)] AS labels, relationships(path) AS rels
    """
    result = await session.run(query, id=entity_id)
    records = await result.data()

    nodes_dict: Dict[str, Dict[str, Any]] = {}
    edges_list = []
    for r in records:
        for node, lbls in zip(r["nodes"], r["labels"]):
            nid = str(node.get("id") or node["id"])
            if nid not in nodes_dict:
                props = dict(node)
                nodes_dict[nid] = {
                    "id": nid,
                    "label": props.get("name") or props.get("cin")
                    or props.get("normalized_address") or props.get("invoice_no")
                    or props.get("din") or nid,
                    "type": lbls[0] if lbls else "Unknown",
                    "properties": _sanitize(props),
                }
        for rel in r["rels"]:
            if isinstance(rel, tuple) and len(rel) >= 3:
                src = str(rel[0].get("id") or "")
                tgt = str(rel[2].get("id") or "")
                rtype = rel[1] if isinstance(rel[1], str) else "TRANSACTS_WITH"
                rprops = rel[3] if len(rel) > 3 and isinstance(rel[3], dict) else {}
            else:
                src = str(rel.get("source") or rel.get("start_node") or "")
                tgt = str(rel.get("target") or rel.get("end_node") or "")
                rtype = rel.get("type", "")
                rprops = dict(rel)
            edges_list.append({
                "source": src,
                "target": tgt,
                "type": rtype,
                "properties": _sanitize(rprops),
            })

    seen_edges = set()
    unique_edges = []
    for e in edges_list:
        key = (e["source"], e["target"], e["type"])
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)

    flagged = await _flagged_cycle_edges(session, entity_id)
    for e in unique_edges:
        e["flagged"] = (e["source"], e["target"], e["type"]) in flagged

    return {"nodes": list(nodes_dict.values()), "edges": unique_edges}


async def _flagged_cycle_edges(session, entity_id: str) -> Set[Tuple[str, str, str]]:
    """Invoice edges (company -> txn -> company) that form a detected
    circular-trading ring involving the entity. Used by the UI to paint
    flagged-cycle edges red (TRD §4.6)."""
    flagged: Set[Tuple[str, str, str]] = set()
    try:
        ring_query = f"""
        MATCH path = (c1:Company {{id: $id}}) ((:Company)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(:Company)){{2,{settings.max_cycle_hops}}} (c1)
        WITH [n IN nodes(path) WHERE n:Company] AS comps
        RETURN comps
        LIMIT $limit
        """
        result = await session.run(ring_query, id=entity_id, limit=settings.max_ring_paths)
        ring_ids: Set[str] = set()
        for rec in await result.data():
            for c in rec["comps"]:
                cid = str(c.get("id") or c["id"]) if isinstance(c, dict) else str(c.id)
                ring_ids.add(cid)
        if not ring_ids:
            return flagged
        edge_query = """
        MATCH (a:Company)-[:BILLED]->(t:Transaction)-[:BILLED_TO]->(b:Company)
        WHERE a.id IN $ring AND b.id IN $ring
        RETURN a.id AS a, t.id AS t, b.id AS b
        """
        result = await session.run(edge_query, ring=list(ring_ids))
        for rec in await result.data():
            flagged.add((str(rec["a"]), str(rec["t"]), "BILLED"))
            flagged.add((str(rec["t"]), str(rec["b"]), "BILLED_TO"))
    except Exception:
        pass
    return flagged


async def get_timeline(session, entity_id: str) -> List[Dict[str, Any]]:
    query = """
    MATCH (c:Company {id: $id})-[:BILLED]->(t:Transaction)-[:BILLED_TO]->(other:Company)
    RETURN t, other
    ORDER BY t.invoice_date
    """
    result = await session.run(query, id=entity_id)
    records = await result.data()
    timeline = []
    for r in records:
        t = r["t"]
        other = r["other"]
        timeline.append({
            "date": str(t.get("invoice_date", "")),
            "amount": t.get("amount", 0),
            "seller_gstin": t.get("gstin_seller", ""),
            "buyer_gstin": t.get("gstin_buyer", ""),
            "return_period": t.get("return_period", ""),
            "counterparty": {
                "id": other.get("id", ""),
                "name": other.get("name", ""),
                "cin": other.get("cin", ""),
            },
        })
    return timeline


def _canonical_cycle(path_ids: List[str]) -> tuple:
    """Canonical key for a simple cycle: min over rotations and reversal,
    so J-K-L, K-L-J, and L-K-J all map to the same ring."""
    ids = list(path_ids)
    variants = [tuple(ids[i:] + ids[:i]) for i in range(len(ids))]
    rev = list(reversed(ids))
    variants += [tuple(rev[i:] + rev[:i]) for i in range(len(rev))]
    return min(variants)


async def get_loops(session, max_length: int, cin: Optional[str] = None) -> Dict[str, Any]:
    # Each repetition of the company hop adds one company, so the smallest
    # closed ring needs (min_cycle_length - 1) repetitions.
    #
    # NOTE on hop_count: the returned ``length`` is the number of *invoice
    # edges* in the closed cycle. For a simple ring (each company appearing
    # once) that equals the number of distinct companies. The Cypher path
    # below re-ends on its start company, so ``comps`` contains the start
    # twice; we dedup to distinct companies and use that count directly.
    min_repeats = settings.min_cycle_length - 1
    if not (min_repeats <= max_length <= settings.max_cycle_hops):
        max_length = settings.loops_default_max_length
    company_hop = "((:Company)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(:Company))"
    if cin:
        query = f"""
        MATCH path = (c1:Company {{cin: $cin}}) {company_hop}{{{min_repeats},{max_length}}} (c1)
        WITH [n IN nodes(path) WHERE n:Company] AS comps,
             [n IN nodes(path) WHERE n:Transaction | coalesce(n.amount, 0)] AS amounts
        RETURN comps, amounts
        LIMIT $limit
        """
        limit = settings.max_entity_loop_paths
    else:
        query = f"""
        MATCH path = (c1:Company) {company_hop}{{{min_repeats},{max_length}}} (c1)
        WITH [n IN nodes(path) WHERE n:Company] AS comps,
             [n IN nodes(path) WHERE n:Transaction | coalesce(n.amount, 0)] AS amounts
        RETURN comps, amounts
        LIMIT $limit
        """
        limit = settings.max_global_loop_paths
    result = await session.run(query, cin=cin, limit=limit)
    records = await result.data()

    loops = []
    seen_paths = set()
    for r in records:
        comps = r["comps"]
        raw_ids = [str(c.get("id") or c["id"]) if isinstance(c, dict) else str(c.id) for c in comps]
        path_ids = list(dict.fromkeys(raw_ids))
        ring_key = _canonical_cycle(path_ids)
        if ring_key in seen_paths:
            continue
        seen_paths.add(ring_key)
        total_amount = sum(r.get("amounts") or [])
        loops.append(_sanitize({
            "path": path_ids,
            # hop_count = number of invoice edges = distinct companies in a
            # simple closed ring. ``path_ids`` is already deduped, so no -1.
            "length": len(path_ids),
            "total_amount": total_amount,
            "companies": [dict(c) for c in comps],
        }))

    loops = [l for l in loops if l["length"] >= settings.min_cycle_length]
    return {"loops": loops, "total": len(loops)}


async def _ensure_invoice_graph(session, name: Optional[str] = None) -> None:
    name = name or settings.gds_projection_name
    try:
        await session.run(f"CALL gds.graph.drop('{name}', false) YIELD graphName RETURN graphName")
    except Exception:
        pass
    await session.run(
        "CALL gds.graph.project.cypher($name, "
        "'MATCH (c:Company) RETURN id(c) AS id', "
        "'MATCH (a:Company)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(b:Company) "
        "RETURN id(a) AS source, id(b) AS target') "
        "YIELD graphName RETURN graphName",
        name=name,
    )


async def compute_wcc(session) -> Dict[str, Any]:
    try:
        await _ensure_invoice_graph(session)
        result = await session.run(f"""
        CALL gds.wcc.write('{settings.gds_projection_name}', {{
            writeProperty: 'community_id'
        }})
        YIELD componentCount, nodePropertiesWritten
        RETURN componentCount, nodePropertiesWritten
        """)
        record = await result.single()
        return {
            "message": "WCC computed",
            "components": record["componentCount"] if record else 0,
            "nodes_written": record["nodePropertiesWritten"] if record else 0,
        }
    except Exception as e:
        return {"error": str(e), "message": "GDS may not be available"}


async def compute_centrality(session, cin: str) -> Dict[str, Any]:
    try:
        await _ensure_invoice_graph(session)
        pr_result = await session.run(f"""
        CALL gds.pageRank.stream('{settings.gds_projection_name}')
        YIELD nodeId, score
        WHERE gds.util.asNode(nodeId).cin = $cin
        RETURN score
        """, cin=cin)
        pr_record = await pr_result.single()

        bt_result = await session.run(f"""
        CALL gds.betweenness.stream('{settings.gds_projection_name}')
        YIELD nodeId, score
        WHERE gds.util.asNode(nodeId).cin = $cin
        RETURN score
        """, cin=cin)
        bt_record = await bt_result.single()

        return {
            "cin": cin,
            "pagerank": pr_record["score"] if pr_record else None,
            "betweenness": bt_record["score"] if bt_record else None,
        }
    except Exception as e:
        return {"error": str(e), "message": "GDS may not be available"}


async def run_structural_analytics(session) -> Dict[str, Any]:
    """Materialize FraudCycle and FraudCommunity nodes (Backend Schema §2.3),
    write back community_id + centrality + risk_score per company."""
    summary = {"cycles_created": 0, "communities_created": 0, "scored": 0}

    # Project the transaction graph once, reuse for all GDS calls
    try:
        await _ensure_invoice_graph(session)
        summary["graph_projected"] = True
    except Exception as e:
        summary["graph_projection_error"] = str(e)

    # --- 1. Detect and materialize cycles ---
    try:
        result = await session.run(f"""
        MATCH path = (c1:Company) ((:Company)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(:Company)){{2,{settings.max_cycle_hops}}} (c1)
        WITH [n IN nodes(path) WHERE n:Company] AS comps,
             [n IN nodes(path) WHERE n:Transaction | coalesce(n.amount, 0)] AS amounts
        WITH [c IN comps | c.cin] AS cins, comps, amounts
        WHERE size(cins) >= {settings.min_cycle_length}
        RETURN DISTINCT cins,
               reduce(s = 0.0, a IN amounts | s + a) AS total_amount
        LIMIT $limit
        """, limit=settings.max_cycle_paths)
        records = await result.data()
        seen_sets = set()
        for r in records:
            cins = r["cins"]
            dedup = list(dict.fromkeys(cins))
            if len(dedup) < settings.min_cycle_length:
                continue
            key_set = tuple(sorted(dedup))
            if key_set in seen_sets:
                continue
            seen_sets.add(key_set)
            key = "|".join(sorted(dedup))
            await session.run("""
            MERGE (cy: FraudCycle {id: $key})
            SET cy.hop_count = $hop_count,
                cy.company_count = $company_count,
                cy.total_amount = $total_amount,
                cy.member_cins = $cins,
                cy.detected_at = datetime(),
                cy.algorithm_version = 'structural-v1'
            WITH cy
            MATCH (c:Company) WHERE c.cin IN $cins
            MERGE (c)-[:MEMBER_OF_CYCLE]->(cy)
            """, key=key, hop_count=len(dedup), company_count=len(dedup),
                 total_amount=r["total_amount"], cins=dedup)
            summary["cycles_created"] += 1
    except Exception as e:
        summary["cycles_error"] = str(e)

    # --- 2. Louvain communities, write back community_id ---
    try:
        result = await session.run(f"""
        CALL gds.louvain.write('{settings.gds_projection_name}', {{
            writeProperty: 'community_id',
            maxIterations: {settings.gds_louvain_max_iterations}
        }})
        YIELD communityCount, nodePropertiesWritten
        RETURN communityCount, nodePropertiesWritten
        """)
        record = await result.single()
        summary["communities"] = record["communityCount"] if record else 0
        summary["community_nodes_written"] = record["nodePropertiesWritten"] if record else 0

        comm_result = await session.run(f"""
        CALL gds.louvain.stream('{settings.gds_projection_name}', {{maxIterations: {settings.gds_louvain_max_iterations}}})
        YIELD nodeId, communityId
        WITH communityId, collect(gds.util.asNode(nodeId)) AS members
        RETURN communityId, size(members) AS member_count,
               [m IN members | m.cin] AS cins
        """)
        for r in await comm_result.data():
            await session.run("""
            MERGE (fc: FraudCommunity {id: $cid})
            SET fc.member_count = $member_count,
                fc.member_cins = $cins,
                fc.detected_at = datetime(),
                fc.algorithm_version = 'louvain-v1'
            WITH fc
            UNWIND $cins AS cin
            MATCH (c:Company {cin: cin})
            MERGE (c)-[:MEMBER_OF_COMMUNITY]->(fc)
            """, cid=str(r["communityId"]), member_count=r["member_count"], cins=r["cins"])
            summary["communities_created"] += 1
    except Exception as e:
        summary["communities_error"] = str(e)

    # --- 3. Centrality write-back ---
    try:
        await session.run(f"""
        CALL gds.pageRank.write('{settings.gds_projection_name}', {{writeProperty: 'pagerank'}})
        YIELD nodePropertiesWritten
        RETURN nodePropertiesWritten
        """)
        summary["pagerank_written"] = True
    except Exception as e:
        summary["pagerank_error"] = str(e)

    # --- 4. Risk scoring (heuristic, explainable) ---
    try:
        result = await session.run("""
        MATCH (c:Company)
        OPTIONAL MATCH (c)-[:MEMBER_OF_CYCLE]->(cy: FraudCycle)
        OPTIONAL MATCH (c)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(nei:Company)
        OPTIONAL MATCH (c)<-[:DIRECTOR_OF]-(d:Director)-[:DIRECTOR_OF]->(other:Company)
        WHERE other <> c
        OPTIONAL MATCH (c)-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(sameaddr:Company)
        WHERE sameaddr <> c
        WITH c,
             count(DISTINCT cy) AS cycle_count,
             count(DISTINCT nei) AS degree,
             count(DISTINCT other) AS shared_director_count,
             count(DISTINCT sameaddr) AS shared_address_count,
             coalesce(c.pagerank, 0.0) AS pagerank,
             coalesce(c.betweenness, 0.0) AS betweenness,
             coalesce(c.paid_up_capital, 0.0) AS puc
        RETURN c.cin AS cin,
               cycle_count, degree, shared_director_count, shared_address_count,
               pagerank, betweenness, puc
        """)
        records = await result.data()
        for r in records:
            score = _heuristic_risk_score(r)
            await session.run(
                "MATCH (c:Company {cin: $cin}) "
                "SET c.risk_score = $score, c.risk_source = 'heuristic', c.updated_at = datetime()",
                cin=r["cin"], score=score
            )
            summary["scored"] += 1
    except Exception as e:
        summary["risk_error"] = str(e)

    return summary


def _heuristic_risk_score(features: Dict[str, Any]) -> float:
    """Rule-based 0-100 score combining structural red flags. Explainable and
    independent of any ML layer (PRD NFR reliability). All weights are
    configurable via settings/environment."""
    score = 0.0
    cycle_count = features.get("cycle_count") or 0
    degree = features.get("degree") or 0
    shared_director = features.get("shared_director_count") or 0
    shared_address = features.get("shared_address_count") or 0
    pagerank = features.get("pagerank") or 0.0
    betweenness = features.get("betweenness") or 0.0

    if cycle_count > 0:
        score += settings.risk_cycle_base + min(
            settings.risk_cycle_cap,
            cycle_count * settings.risk_cycle_step,
        )
    if shared_director > 0:
        score += min(
            settings.risk_director_cap,
            shared_director * settings.risk_director_weight,
        )
    if shared_address > 0:
        score += min(
            settings.risk_address_cap,
            shared_address * settings.risk_address_weight,
        )
    if degree >= settings.risk_degree_min:
        score += min(
            settings.risk_degree_cap,
            (degree - 1) * settings.risk_degree_weight,
        )
    score += min(settings.risk_pagerank_cap, pagerank * settings.risk_pagerank_weight)
    score += min(
        settings.risk_betweenness_cap,
        betweenness * settings.risk_betweenness_weight,
    )
    return round(min(score, settings.risk_score_cap), 1)


async def trigger_risk_job(session) -> Dict[str, Any]:
    return await run_structural_analytics(session)


async def _cycle_invoices(session, cins: List[str]) -> Dict[str, Any]:
    """Return the real invoice edges among a set of ring companies, plus the
    date span. These are the BILLED->Transaction->BILLED_TO edges that make up
    the loop — not a template. Ordered by invoice_date."""
    if not cins:
        return {"invoices": [], "date_span": None}
    result = await session.run("""
    MATCH (a:Company)-[:BILLED]->(t:Transaction)-[:BILLED_TO]->(b:Company)
    WHERE a.cin IN $cins AND b.cin IN $cins
    RETURN t.invoice_no AS invoice_no,
           a.cin AS seller_cin, a.name AS seller_name, a.gstin AS seller_gstin,
           b.cin AS buyer_cin, b.name AS buyer_name, b.gstin AS buyer_gstin,
           t.amount AS amount,
           coalesce(t.invoice_date, t.date) AS invoice_date
    ORDER BY coalesce(t.invoice_date, t.date)
    """, cins=cins)
    rows = await result.data()
    invoices = []
    dates = []
    for r in rows:
        d = _sanitize(dict(r))
        invoices.append(d)
        if d.get("invoice_date") is not None:
            dates.append(str(d["invoice_date"])[:10])
    date_span = None
    if dates:
        first, last = dates[0], dates[-1]
        span_days = None
        try:
            from datetime import date as _date
            y1, m1, d1 = (int(x) for x in first.split("-")[:3])
            y2, m2, d2 = (int(x) for x in last.split("-")[:3])
            span_days = (_date(y2, m2, d2) - _date(y1, m1, d1)).days
        except Exception:
            span_days = None
        date_span = {
            "first": first,
            "last": last,
            "span_days": span_days,
            "invoice_dates": len(set(dates)),
        }
    return {"invoices": invoices, "date_span": date_span}


async def explain_entity(session, entity_id: str) -> Dict[str, Any]:
    """Return the evidence subgraph + plain-language reason for the flag
    (TRD §4.6, FR7).

    METHOD LABEL: the explanation is *structural subgraph attribution* — it is
    assembled from the detected structures that drove the score (the FraudCycle
    the entity belongs to, its Louvain FraudCommunity, shared directors /
    addresses / bank accounts, and the entity's centrality/risk feature
    values). It is NOT PyG ``GNNExplainer`` (learned attribution). This is
    surfaced to clients as ``evidence.method == "subgraph_attribution"``.
    """
    entity = await get_entity(session, entity_id)
    if not entity:
        return None
    cin = entity.get("cin")
    reasons = []
    evidence = {
        "method": "subgraph_attribution",
        "cycles": [],
        "communities": [],
        "shared_directors": [],
        "shared_addresses": [],
        "shared_bank_accounts": [],
        "risk": entity.get("risk_score"),
        "risk_decomposition": None,
    }

    # --- FraudCycle(s) the entity is a member of (the loop that drove the score)
    cyc = await session.run("""
    MATCH (c:Company {id: $id})-[:MEMBER_OF_CYCLE]->(cy: FraudCycle)
    RETURN cy
    """, id=entity_id)
    for r in await cyc.data():
        cy = r["cy"]
        cins = cy.get("member_cins") or []
        members = []
        mres = await session.run(
            "MATCH (c:Company) WHERE c.cin IN $cins "
            "RETURN c.cin AS cin, c.name AS name, c.gstin AS gstin ORDER BY c.cin",
            cins=cins
        )
        for m in await mres.data():
            members.append(_sanitize(dict(m)))
        inv_block = await _cycle_invoices(session, cins)
        company_count = cy.get("company_count") or len(cins)
        hop_count = cy.get("hop_count") or company_count
        total = cy.get("total_amount") or 0
        evidence["cycles"].append(_sanitize({
            "cycle_id": cy.get("id"),
            "hop_count": hop_count,
            "company_count": company_count,
            "total_invoice_amount": total,
            "date_span": inv_block["date_span"],
            "companies": members,
            "invoices": inv_block["invoices"],
        }))
        span = inv_block["date_span"]
        span_str = f", over {span['span_days']} days" if span and span.get("span_days") is not None else ""
        reasons.append(
            f"Flagged because it forms a {hop_count}-hop invoice cycle across "
            f"{company_count} companies, totaling ₹{total:,.0f}{span_str}"
            + (f" ({inv_block['invoices'][0]['invoice_no']}…{inv_block['invoices'][-1]['invoice_no']})"
               if inv_block["invoices"] and inv_block["invoices"][0].get("invoice_no") else "")
        )

    # --- Louvain FraudCommunity membership (may be more than one per entity)
    comm = await session.run("""
    MATCH (c:Company {id: $id})-[:MEMBER_OF_COMMUNITY]->(fc: FraudCommunity)
    OPTIONAL MATCH (m:Company)-[:MEMBER_OF_COMMUNITY]->(fc)
    RETURN fc.id AS community_id, fc.member_count AS member_count,
           collect(DISTINCT m.cin) AS member_cins
    """, id=entity_id)
    for r in await comm.data():
        evidence["communities"].append(_sanitize(dict(r)))

    # --- Shared directors
    sd = await session.run("""
    MATCH (c:Company {id: $id})<-[:DIRECTOR_OF]-(d:Director)-[:DIRECTOR_OF]->(other:Company)
    WHERE other <> c
    RETURN DISTINCT d.name AS director, d.din AS din,
           collect(DISTINCT other.name) AS companies,
           collect(DISTINCT other.cin) AS cins
    """, id=entity_id)
    for r in await sd.data():
        evidence["shared_directors"].append(_sanitize(dict(r)))
        reasons.append(
            f"Shares director '{r['director']}' with {len(r['companies'])} other company(ies)"
        )

    # --- Shared addresses
    sa = await session.run("""
    MATCH (c:Company {id: $id})-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(other:Company)
    WHERE other <> c
    RETURN DISTINCT a.raw_address AS address, a.state AS state,
           collect(DISTINCT other.name) AS companies
    """, id=entity_id)
    for r in await sa.data():
        evidence["shared_addresses"].append(_sanitize(dict(r)))
        reasons.append(
            f"Shares registered address '{r['address']}' with {len(r['companies'])} other company(ies)"
        )

    # --- Shared bank accounts (OPERATES_ACCOUNT + BankAccount)
    sba = await session.run("""
    MATCH (c:Company {id: $id})-[:OPERATES_ACCOUNT]->(b:BankAccount)<-[:OPERATES_ACCOUNT]-(other:Company)
    WHERE other <> c
    RETURN DISTINCT b.ifsc AS ifsc, b.account_hash AS account_hash,
           collect(DISTINCT other.name) AS companies
    """, id=entity_id)
    for r in await sba.data():
        evidence["shared_bank_accounts"].append(_sanitize(dict(r)))
        reasons.append(
            f"Operates bank account {r['ifsc']} jointly with {len(r['companies'])} other company(ies)"
        )

    # --- Risk decomposition (feature attribution for the heuristic score).
    # Mirrors _heuristic_risk_score so every component is the number that
    # actually contributed to the flag.
    shared_dir_count = len(evidence["shared_directors"])
    shared_addr_count = len(evidence["shared_addresses"])
    pr = float(entity.get("pagerank") or 0)
    cycle_terms = [c for c in evidence["cycles"]]
    cycle_component = 0.0
    if cycle_terms:
        cycle_component = settings.risk_cycle_base + min(
            settings.risk_cycle_cap, len(cycle_terms) * settings.risk_cycle_step)
    dir_component = min(settings.risk_director_cap,
                        shared_dir_count * settings.risk_director_weight) if shared_dir_count else 0.0
    addr_component = min(settings.risk_address_cap,
                         shared_addr_count * settings.risk_address_weight) if shared_addr_count else 0.0
    degree = entity.get("degree")
    if degree is None:
        deg_res = await session.run("""
        MATCH (c:Company {id: $id})-[:BILLED]->(:Transaction)-[:BILLED_TO]->(nei:Company)
        RETURN count(DISTINCT nei) AS degree
        """, id=entity_id)
        deg_rec = await deg_res.single()
        degree = deg_rec["degree"] if deg_rec else 0
    degree_component = min(settings.risk_degree_cap,
                           (degree - 1) * settings.risk_degree_weight) if degree >= settings.risk_degree_min else 0.0
    pr_component = min(settings.risk_pagerank_cap, pr * settings.risk_pagerank_weight)
    bt = float(entity.get("betweenness") or 0.0)
    bt_component = min(settings.risk_betweenness_cap, bt * settings.risk_betweenness_weight)
    evidence["risk_decomposition"] = _sanitize({
        "cycle": cycle_component,
        "shared_director": dir_component,
        "shared_address": addr_component,
        "degree": degree_component,
        "degree_value": degree,
        "pagerank": round(pr_component, 2),
        "betweenness": round(bt_component, 2),
        "source": entity.get("risk_source"),
    })

    if pr > 0.05:
        reasons.append(f"Elevated network centrality (PageRank {pr:.3f})")

    if not reasons:
        reasons.append("No structural red flags detected in the current graph snapshot.")

    return {
        "entity": _sanitize({k: v for k, v in entity.items() if k != "_labels"}),
        "reasons": reasons,
        "evidence": evidence,
    }


def _jaro_winkler(a: str, b: str,
                  prefix_scale: Optional[float] = None,
                  prefix_max: Optional[int] = None) -> float:
    """Jaro-Winkler similarity, pure-python (no external dep). Returns 0..1."""
    if prefix_scale is None:
        prefix_scale = settings.entity_resolution_prefix_scale
    if prefix_max is None:
        prefix_max = settings.entity_resolution_prefix_max
    a, b = a.strip().lower(), b.strip().lower()
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    len_a, len_b = len(a), len(b)
    match_dist = max(len_a, len_b) // 2 - 1
    match_dist = max(match_dist, 0)

    a_matches = [False] * len_a
    b_matches = [False] * len_b
    matches = 0
    for i, ca in enumerate(a):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len_b)
        for j in range(start, end):
            if not b_matches[j] and b[j] == ca:
                a_matches[i] = True
                b_matches[j] = True
                matches += 1
                break

    if matches == 0:
        return 0.0

    transpositions = 0
    k = 0
    for i in range(len_a):
        if a_matches[i]:
            while not b_matches[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    transpositions //= 2

    jaro = (matches / len_a + matches / len_b + (matches - transpositions) / matches) / 3.0

    prefix = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        prefix += 1
        if prefix == prefix_max:
            break
    return jaro + prefix * prefix_scale * (1.0 - jaro)


async def run_entity_resolution(session, fuzzy_threshold: Optional[float] = None) -> Dict[str, Any]:
    """Phase 2 entity resolution (Backend Schema §2.2):
    - deterministic: shared DIN / normalized address / bank IFSC+account_hash
    - fuzzy: Jaro-Winkler name similarity, confidence-scored
    Writes :RESOLVED_AS edges between companies."""
    if fuzzy_threshold is None:
        fuzzy_threshold = settings.entity_resolution_fuzzy_threshold
    summary = {"resolved_edges": 0, "deterministic": 0, "fuzzy": 0}

    # --- Deterministic: directors with same DIN ---
    dres = await session.run("""
    MATCH (c:Company)<-[:DIRECTOR_OF]-(d:Director)
    WITH d.din AS din, collect(DISTINCT c) AS companies
    WHERE size(companies) > 1
    UNWIND companies AS c
    WITH din, companies, c
    MATCH (other:Company)
    WHERE other IN companies AND other <> c
    MERGE (c)-[:RESOLVED_AS {method: 'deterministic', key_type: 'din', key_value: din}]->(other)
    """)
    summary["deterministic"] += (await dres.consume()).counters.relationships_created or 0

    # --- Deterministic: companies sharing a normalized registered address ---
    ares = await session.run("""
    MATCH (c:Company)-[:REGISTERED_AT]->(a:Address)
    WITH a.normalized_address AS addr, collect(DISTINCT c) AS companies
    WHERE size(companies) > 1
    UNWIND companies AS c
    WITH addr, companies, c
    MATCH (other:Company)
    WHERE other IN companies AND other <> c
    MERGE (c)-[:RESOLVED_AS {method: 'deterministic', key_type: 'address', key_value: addr}]->(other)
    """)
    summary["deterministic"] += (await ares.consume()).counters.relationships_created or 0

    # --- Deterministic: companies operating the same bank account (IFSC + account_hash) ---
    bres = await session.run("""
    MATCH (c:Company)-[:OPERATES_ACCOUNT]->(b:BankAccount)
    WITH b.ifsc AS ifsc, b.account_hash AS acc, collect(DISTINCT c) AS companies
    WHERE size(companies) > 1
    UNWIND companies AS c
    WITH ifsc, acc, companies, c
    MATCH (other:Company)
    WHERE other IN companies AND other <> c
    MERGE (c)-[:RESOLVED_AS {method: 'deterministic', key_type: 'bank', key_value: ifsc + ':' + acc}]->(other)
    """)
    summary["deterministic"] += (await bres.consume()).counters.relationships_created or 0

    # --- Fuzzy: Jaro-Winkler name similarity above threshold ---
    fres = await session.run("""
    MATCH (c:Company)
    WITH collect(DISTINCT c) AS companies
    UNWIND companies AS c1
    UNWIND companies AS c2
    WITH c1, c2
    WHERE c1 <> c2 AND id(c1) < id(c2) AND c1.cin IS NOT NULL AND c2.cin IS NOT NULL
    RETURN c1.cin AS cin1, c2.cin AS cin2,
           c1.name AS name1, c2.name AS name2,
           size([(c1)-[r:RESOLVED_AS]-(c2) | r]) AS already
    """)
    for r in await fres.data():
        if r["already"] > 0:
            continue
        if r["name1"] is None or r["name2"] is None:
            continue
        score = _jaro_winkler(r["name1"], r["name2"])
        if score >= fuzzy_threshold:
            await session.run("""
            MATCH (a:Company {cin: $cin1}), (b:Company {cin: $cin2})
            MERGE (a)-[:RESOLVED_AS {method: 'fuzzy', key_type: 'name_similarity',
                                     confidence: $conf}]->(b)
            """, cin1=r["cin1"], cin2=r["cin2"], conf=round(score, 3))
            summary["fuzzy"] += 1

    summary["resolved_edges"] = summary["deterministic"] + summary["fuzzy"]
    return summary


async def get_stats_overview(session, db) -> Dict[str, Any]:
    from sqlalchemy import text
    comps = await session.run("MATCH (c:Company) RETURN count(c) AS n")
    companies = (await comps.single())["n"] if comps else 0

    cycles = await session.run("MATCH (cy: FraudCycle) RETURN count(cy) AS n")
    cycle_count = (await cycles.single())["n"] if cycles else 0

    flagged = await session.run(
        "MATCH (c:Company) WHERE c.risk_score >= $threshold RETURN count(c) AS n",
        threshold=settings.risk_flag_threshold,
    )
    flagged_count = (await flagged.single())["n"] if flagged else 0

    at_risk = await session.run("""
    MATCH (c:Company) WHERE c.risk_score >= $threshold
    OPTIONAL MATCH (c)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(n:Company)
    WITH c, n
    RETURN sum(coalesce(c.paid_up_capital, 0)) AS total
    """, threshold=settings.risk_flag_threshold)
    at_risk_total = (await at_risk.single())["total"] or 0

    top_state = await session.run("""
    MATCH (c:Company)-[:REGISTERED_AT]->(a:Address)
    WHERE c.risk_score >= $threshold
    RETURN a.state AS state, count(c) AS n
    ORDER BY n DESC LIMIT 1
    """, threshold=settings.risk_flag_threshold)
    tr = await top_state.single()
    top_state_name = tr["state"] if tr and tr["state"] else "N/A"

    directors = await session.run("MATCH (d:Director) RETURN count(d) AS n")
    director_count = (await directors.single())["n"] if directors else 0

    open_cases = 0
    try:
        result = await db.execute(text("SELECT count(*) FROM cases WHERE status IN ('open','in_progress')"))
        open_cases = result.scalar() or 0
    except Exception:
        pass

    return {
        "companies": companies,
        "directors": director_count,
        "flagged_entities": flagged_count,
        "cycles_detected": cycle_count,
        "estimated_itc_at_risk": round(float(at_risk_total or 0), 2),
        "top_risk_state": top_state_name,
        "open_cases": open_cases,
    }


async def get_worklist(session, sort: str, direction: str, state: Optional[str],
                       sector: Optional[str], min_score: Optional[float],
                       max_score: Optional[float], page: int, page_size: int) -> Dict[str, Any]:
    allowed = {
        "risk_score": "c.risk_score",
        "name": "c.name",
        "paid_up_capital": "c.paid_up_capital",
        "incorporation_date": "c.incorporation_date",
    }
    sort_key = allowed.get(sort, "c.risk_score")
    direction = "DESC" if direction.lower() == "desc" else "ASC"

    where = []
    params = {}
    # NOTE: predicates must be evaluated in a WHERE that is NOT part of the
    # OPTIONAL MATCH below — a WHERE directly after OPTIONAL MATCH becomes part
    # of that optional pattern and only nulls the binding instead of filtering
    # rows. Bind the filters on the Company match (EXISTS subquery for address).
    if state:
        where.append("EXISTS { MATCH (c)-[:REGISTERED_AT]->(:Address {state: $state}) }")
        params["state"] = state
    if sector:
        where.append("c.nic_code = $sector")
        params["sector"] = sector
    if min_score is not None:
        where.append("c.risk_score >= $min_score")
        params["min_score"] = min_score
    if max_score is not None:
        where.append("c.risk_score <= $max_score")
        params["max_score"] = max_score

    where_clause = " AND ".join(where)
    where_clause = f"WHERE {where_clause}" if where_clause else ""

    count_query = f"""
    MATCH (c:Company)
    {where_clause}
    RETURN count(DISTINCT c) AS total
    """
    cnt = await session.run(count_query, **params)
    total = (await cnt.single())["total"] or 0

    query = f"""
    MATCH (c:Company)
    {where_clause}
    WITH c
    OPTIONAL MATCH (c)-[:REGISTERED_AT]->(a:Address)
    WITH c, a
    OPTIONAL MATCH (c)-[:MEMBER_OF_CYCLE]->(cy: FraudCycle)
    WITH c, a, count(cy) AS cycle_count
    RETURN c.cin AS cin, c.gstin AS gstin, c.name AS name, c.risk_score AS risk_score,
           c.status AS status, c.nic_code AS nic_code, a.state AS state,
           c.paid_up_capital AS paid_up_capital, c.incorporation_date AS incorporation_date,
           c.pagerank AS pagerank, c.community_id AS community_id, c.risk_source AS risk_source,
           cycle_count
    ORDER BY {sort_key} {direction}
    SKIP $skip LIMIT $limit
    """
    params["skip"] = (page - 1) * page_size
    params["limit"] = page_size
    result = await session.run(query, **params)
    records = await result.data()

    items = []
    for r in records:
        items.append({
            "cin": r["cin"], "gstin": r["gstin"], "name": r["name"],
            "risk_score": r["risk_score"], "status": r["status"],
            "nic_code": r["nic_code"], "state": r["state"],
            "paid_up_capital": r["paid_up_capital"],
            "incorporation_date": str(r["incorporation_date"]) if r["incorporation_date"] else None,
            "pagerank": r["pagerank"], "community_id": r["community_id"],
            "cycle_count": r["cycle_count"], "risk_source": r.get("risk_source"),
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}

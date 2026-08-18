# Structural Analytics Queries - per 02_TRD.md §4.1-4.3
# Invoice edge in schema §2.2: (seller)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(buyer)

# ---------------------------------------------------------------
# 4.1 Cycle Detection (TRD: MATCH p = (c:Company)-[:ISSUED_INVOICE_TO*3..8]->(c))
# Quantified path pattern equivalent through :Transaction nodes.
# ---------------------------------------------------------------
MATCH p = (start:Company) ((:Company)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(:Company)){3,8} (start)
RETURN start.cin AS start_cin,
       [n IN nodes(p) WHERE n:Company | n.cin] AS cycle_companies,
       [n IN nodes(p) WHERE n:Transaction | n.amount] AS amounts,
       size([n IN nodes(p) WHERE n:Company]) - 1 AS hop_count,
       reduce(s = 0.0, a IN [n IN nodes(p) WHERE n:Transaction | n.amount] | s + a) AS total_invoice_amount

# ---------------------------------------------------------------
# 4.2 Community Detection - WCC then Louvain on the company-level graph
# ---------------------------------------------------------------
CALL gds.graph.project.cypher('company_invoice_graph',
  'MATCH (c:Company) RETURN id(c) AS id',
  'MATCH (a:Company)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(b:Company) RETURN id(a) AS source, id(b) AS target')

CALL gds.wcc.stream('company_invoice_graph')
YIELD nodeId, componentId
RETURN gds.util.asNode(nodeId).name AS company, componentId
ORDER BY componentId, company

CALL gds.louvain.stream('company_invoice_graph')
YIELD nodeId, communityId
RETURN gds.util.asNode(nodeId).name AS company, communityId
ORDER BY communityId, company

# ---------------------------------------------------------------
# 4.3 Centrality Features (PageRank / betweenness / degree)
# ---------------------------------------------------------------
CALL gds.pageRank.stream('company_invoice_graph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS company, round(score, 4) AS pagerank
ORDER BY pagerank DESC

CALL gds.betweenness.stream('company_invoice_graph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS company, round(score, 2) AS betweenness
ORDER BY betweenness DESC

CALL gds.degree.stream('company_invoice_graph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS company, score AS out_degree
ORDER BY out_degree DESC

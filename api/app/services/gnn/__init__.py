"""Phase 3 GNN layer (Implementation Plan): GraphSAGE-style risk scoring.

Packages: model (GraphSAGE in torch), features (Neo4j -> tensors),
synthetic (AML-style benchmark generator), train (CLI), predict (write-back).
Kept dependency-light: pure torch, no pyg/scatter wheels needed.
"""
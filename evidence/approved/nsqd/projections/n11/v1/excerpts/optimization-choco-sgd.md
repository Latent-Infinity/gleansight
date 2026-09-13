## Decentralized Stochastic Optimization and Gossip Algorithms with Compressed Communication

## Abstract

We consider decentralized stochastic optimization with the objective function (e.g. data samples for machine learning task) being distributed over n machines that can only communicate to their neighbors on a fixed communication graph. To reduce the communication bottleneck, the nodes compress (e.g. quantize or sparsify) their model updates. We cover both unbiased and biased compression operators with quality denoted by ω ≤ 1 ( ω = 1 meaning no compression).

We (i) propose a novel gossip-based stochastic gradient descent algorithm, Choco-SGD , that converges at rate O ( 1 / ( nT ) + 1 / ( Tδ 2 ω ) 2 ) for strongly convex objectives, where T denotes the number of iterations and δ the eigengap of the connectivity matrix. Despite compression quality and network connectivity affecting the higher order terms, the first term in the rate, O (1 / ( nT )), is the same as for the centralized baseline with exact communication.

Formally, we consider optimization problems distributed across n devices or nodes. We also allow each local objective f i to have stochastic optimization (or sum) structure, covering the important case of empirical risk minimization in distributed machine learning and deep learning applications.

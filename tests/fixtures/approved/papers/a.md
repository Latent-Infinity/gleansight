## Distributed Momentum-based Frank-Wolfe Algorithm for Stochastic Optimization

Jie Hou, Xianlin Zeng, Member, IEEE , Gang Wang, Member, IEEE , Jian Sun, Senior Member, IEEE , and Jie Chen, Fellow, IEEE

Abstract -This paper considers distributed stochastic optimization, in which a number of agents cooperate to optimize a global objective function through local computations and information exchanges with neighbors over a network. Stochastic optimization problems are usually tackled by variants of projected stochastic gradient descent. However, projecting a point onto a feasible set is often expensive. The Frank-Wolfe (FW) method has well-documented merits in handling convex constraints, but existing stochastic FW algorithms are basically developed for centralized settings. In this context, the present work puts forth a distributed stochastic Frank-Wolfe solver, by judiciously combining Nesterov's momentum and gradient tracking techniques for stochastic convex and nonconvex optimization over networks. It is shown that the convergence rate of the proposed algorithm is O ( k -1 2 ) for convex optimization, and O (1 / log 2 ( k )) for nonconvex optimization. The efficacy of the algorithm is demonstrated by numerical simulations against a number of competing alternatives.

Index Terms -Distributed Optimization, Frank-Wolfe Algorithms, Stochastic Optimization, Momentum-based Method.

## I. INTRODUCTION

D ISTRIBUTED stochastic optimization is a basic problem that arises widely in diverse engineering applications, including unmanned systems [1]-[3], distributed machine learning [4], and multi-agent reinforcement learning [5]-[7], to name a few. The goal is to minimize a shared objective function, which is defined as the expectation of a set of stochastic functions subject to general convex constraints, by means of local computations and information exchanges between working agents.

This paper considers a set N = { 1 , 2 , · · · , n } of working agents connected through a communication network G =

This work was supported in part by the National Key R &amp; D Program of China under Grant 2021YFB1714800, the National Natural Science Foundation of China under Grants 62073035, 62173034, 61925303, 62088101, 61873033, the CAAI-Huawei MindSpore Open Fund, and the Chongqing Natural Science Foundation under Grant 2021ZX4100027. (Corresponding author: Xianlin Zeng.)

- J. Hou and X. Zeng are with the Key Laboratory of Intelligent Control and Decision of Complex Systems, School of Automation, Beijing Institute of Technology, Beijing, 100081, China (E-mail: [redacted-email]; [redacted-email]).
- G. Wang and J. Sun are with the Key Laboratory of Intelligent Control and Decision of Complex Systems, School of Automation, Beijing Institute of Technology, Beijing, 100081, China and Beijing Institute of Technology Chongqing Innovation Center, Chongqing, 401120, China (E-mail: [redacted-email]; [redacted-email]).
- J. Chen is with the School of Electronic and Information Engineering, Tongji University, Shanghai, 200082, China and also with the Key Laboratory of Intelligent Control and Decision of Complex Systems, School of Automation, Beijing Institute of Technology, Beijing, 100081, China (E-mail: [redacted-email]).

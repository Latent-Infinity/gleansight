LEHIGH

COMPUTATIONAL OPTIMIZATIONI

UNIVERSITY.

COR@L

RESEARCH AT LEHIGH

<!-- image -->

Frank E. Curtis, Michael J. O'Neill, and Daniel P. Robinson

Department of Industrial and Systems Engineering, Lehigh University

COR@L Technical Report 21T-013-R1

<!-- image -->

<!-- image -->

## A Stochastic Sequential Quadratic Optimization Algorithm for Nonlinear Equality Constrained Optimization with Rank-Deficient Jacobians

Albert S. Berahas ∗ 1 , Frank E. Curtis † 2 , Michael J. O'Neill ‡ 2 , and Daniel P. Robinson § 2

1 Department of Industrial and Operations Engineering, University of Michigan 2 Department of Industrial and Systems Engineering, Lehigh University

Original Publication: June 24, 2021

Last Revised: March 17, 2023

## Abstract

A sequential quadratic optimization algorithm is proposed for solving smooth nonlinear equality constrained optimization problems in which the objective function is defined by an expectation of a stochastic function. The algorithmic structure of the proposed method is based on a step decomposition strategy that is known in the literature to be widely effective in practice, wherein each search direction is computed as the sum of a normal step (toward linearized feasibility) and a tangential step (toward objective decrease in the null space of the constraint Jacobian). However, the proposed method is unique from others in the literature in that it both allows the use of stochastic objective gradient estimates and possesses convergence guarantees even in the setting in which the constraint Jacobians may be rank deficient. The results of numerical experiments demonstrate that the algorithm offers superior performance when compared to popular alternatives.

## 1 Introduction

We propose an algorithm for solving equality constrained optimization problems in which the objective function is defined by an expectation of a stochastic function. Formulations of this type arise throughout science and engineering in important applications such as data-fitting problems, where one aims to determine a model that minimizes the discrepancy between values yielded by the model and corresponding known outputs.

Our algorithm is designed for solving such problems when the decision variables are restricted to the solution set of a (potentially nonlinear) set of equations. We are particularly interested in such problems when the constraint Jacobian-i.e., the matrix of first-order derivatives of the constraint function-may be rank deficient in some or even all iterations during the run of an algorithm, since this can be an unavoidable occurrence in practice that would ruin the convergence properties of any algorithm that is not specifically designed for this setting. The structure of our algorithm follows a step decomposition strategy that is

∗ E-mail: [redacted-email]

‡ E-mail: [redacted-email]

† E-mail: [redacted-email]

§ E-mail: [redacted-email]

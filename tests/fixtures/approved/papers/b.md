<!-- image -->

Article

## A Stochastic Optimization Algorithm to Enhance Controllers of Photovoltaic Systems

Samia Charfeddine  1 , Hadeel Alharbi  2 , Houssem Jerbi  3, *, Mourad Kchaou  4 , Rabeh Abbassi  4  and Víctor Leiva  5, *

- 1 Research Unit of Photovoltaic, Wind and Geothermal Systems, National Engineering School of Gabès, University of Gabès, Gabès 6029, Tunisia; [redacted-email] (S.C.)
- 2 Department of Computer Science, College of Computer Science and Engineering, University of Hail, Hail 1234, Saudi Arabia; [redacted-email] (H.A.)
- 3 Department of Industrial Engineering, College of Engineering, University of Hail, Hail 1234, Saudi Arabia
- 4 Department of Electrical Engineering, College of Engineering, University of Hail, Hail 1234, Saudi Arabia; [redacted-email] (M.K.), [redacted-email] (R.A.)
- 5 School of Industrial Engineering, Pontificia Universidad Católica de Valparaíso, Valparaíso 2362807, Chile
* Correspondence: [redacted-email] (H.J.); [redacted-email] or [redacted-email] (V.L.)

Abstract: Increasing energy needs, pollution of nature, and eventual depletion of resources have prompted humanity to obtain new technologies and produce energy using clean sources and renewables. In this paper, we design an advanced method to improve the performance of a sliding mode controller combined with control theory for a photovoltaic system. Specifically, we decouple the controlled output of the system from any perturbation source and assess the effectiveness of the results in terms of solution quality, closed-loop control stability, and dynamical convergence of the state variables. This study focuses on the climatic conditions that may affect the behavior of a solar energy plant to supply a motor with the highest possible efficiency and nominal operating conditions. The designed method enables us to obtain an optimal performance by means of advanced control techniques and a slime mould stochastic optimization algorithm. The efficiency and performance of this method are examined based on a benchmark model of a photovoltaic system via numerical analysis and simulation.

Keywords: control theory; feedback linearization; metaheuristic optimization; numerical analysis; perturbations; simulations; solar energy; state variables; stochasticity

MSC: 93C83

## 1. Introduction

Increasing global energy needs, pollution of nature, and eventual depletion of fossil fuels have prompted humanity to explore new technologies to produce electrical energy using clean sources and renewables, such as solar and wind power [1,2]. However, systems based on wind or solar energies are not stable due to seasonal and daily variations. Indeed, renewable energy systems utilizing a single intermittent source, such as a photovoltaic (PV) system or wind energy, are not stable due to these variations [3-5].

PV systems present problems related to nonlinear characteristics and energy production that depends on climatic conditions which are highly random. Therefore, the design of an optimized PV system becomes difficult. Consequently, the development of efficient techniques to overcome these problems is of paramount importance [6,7].

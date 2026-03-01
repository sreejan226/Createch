# Formwork Decision Intelligence Prototype

Decision intelligence engine for optimizing **formwork BoQ generation, inventory allocation, and multi-site scheduling** using **machine learning, constraint optimization, and rule-based validation**.

This prototype helps reduce excess inventory, avoid shortages, and improve reuse efficiency through automated planning.

---

## Features

- Automated BoQ generation from design and inventory inputs
- Multi-site inventory assignment and transfer optimization
- ML-based demand and productivity forecasting
- Constraint optimization using Google OR-Tools CP-SAT
- Rule validation for reuse limits, safety stock, and compatibility
- FastAPI backend for running optimization and retrieving results

---

## Architecture

Pipeline:

**1. Forecast**
- Predict demand per site and time bucket
- Estimate productivity and cycle time vs inventory

**2. Optimize**
- Assign panels to sites and time periods
- Decide when to purchase vs transfer
- Schedule execution of formwork kits

**3. Validate**
- Enforce reuse limits
- Maintain safety stock
- Check compatibility and constraints

**4. Serve**
- Upload design, inventory, and cost data
- Run optimization in different modes
- Return optimized BoQ and assignments

---

## Optimization Modes

| Mode     | Description                          |
|----------|--------------------------------------|
| LOW_COST | Minimize material and purchase cost |
| BALANCED | Balance cost and project duration   |
| FAST     | Minimize completion time            |

---

## Installation

Clone the repository:

```bash
git clone https://github.com/yourusername/formwork-decision-intelligence.git
cd formwork-decision-intelligence




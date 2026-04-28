# Cloud Cost Review — Q1 2026

**Period:** January 2026
**Total spend:** $14,200/month

---

## Optimization Recommendations

### 1. Enable license benefit on production Windows VMs (HIGH IMPACT)

**Current cost: $2,000/month in VM licenses**

5 production VMs run Windows Server without the Hybrid Benefit applied. If we have qualifying licenses, enabling the benefit eliminates the licensing line item.

#### Action

1. Inventory eligible Windows Server licenses with the IT team.
2. Run `az vm update --license-type Windows_Server` on each VM.

**Potential savings: $1,200-1,500/month**

---

### 2. Exchange wasted reservations

Three reserved VM SKUs have no matching running instances:

- D2s_v3 ×2 — fully wasted
- D4s_v3 ×2 — fully wasted
- B4ms ×1 — fully wasted

#### Action

Exchange via the Azure Portal Reservations blade.

**Estimated savings: $300/month**

---

### 3. Right-size the test SQL databases

UAT databases run at 4× the capacity of QA with no usage justification.

#### Action

Drop UAT SQL databases from 200 DTU to 50 DTU.

**Estimated savings: $280/month**

---

### 4. Delete the unused public IP

`legacy-app-pip` (Standard SKU) is unassociated.

#### Action

Delete the resource.

**Estimated savings: $4/month**

---

## Summary

| # | Action | Savings | Effort | Risk |
|---|---|---|---|---|
| 1 | Enable Hybrid Benefit on prod Windows VMs | $1,200-1,500 | Low | Need licenses |
| 2 | Exchange wasted reservations | $300 | Low | None |
| 3 | Right-size UAT SQL databases | $280 | Low | Monitor after |
| 4 | Delete unused public IP | $4 | Low | None |

**Total estimated savings: $1,800-2,100/month**

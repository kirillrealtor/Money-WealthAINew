"""Mock provider — runs real database tools locally and formats a simulated advisor response.
For development environment use without external API keys.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .provider import AdvisorResult, ToolExecutor


def _float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


class MockProvider:
    name = "mock"

    async def run(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        execute_tool: ToolExecutor,
    ) -> AdvisorResult:
        # Find the last user message
        user_msg = ""
        for m in reversed(messages):
            if m["role"] == "user":
                user_msg = m["content"]
                if isinstance(user_msg, list):
                    user_msg = " ".join([b.get("text", "") for b in user_msg if isinstance(b, dict)])
                break
        
        user_msg_lower = str(user_msg).lower()
        tool_name = "get_account_balances"
        tool_input: dict[str, Any] = {}

        # Heuristics to select the appropriate tool
        if "afford" in user_msg_lower:
            # This is a scripted demo, but its real tool call must still use the requested purchase amount.
            price = re.search(r"(?:USD\s*|\$)(\d+(?:\.\d{1,2})?)", str(user_msg), re.I)
            tool_name = "calculate_affordability"
            tool_input = {"purchase_amount": float(price.group(1)) if price else 100.0, "is_recurring": False}
        elif any(w in user_msg_lower for w in ["spend", "spent", "category", "going", "transaction"]):
            tool_name = "get_spending_summary"
            tool_input = {"period": "last_30d"}
        elif any(
            w in user_msg_lower
            for w in [
                "balance", "cash", "checking", "savings", "liquidity",
                "net worth", "money", "wealth", "asset",
            ]
        ):
            tool_name = "get_account_balances"
            tool_input = {}
        elif any(w in user_msg_lower for w in ["flow", "income", "expense", "surplus", "saving rate", "earning"]):
            tool_name = "get_cash_flow"
            tool_input = {"months": 3}
        elif "budget" in user_msg_lower:
            tool_name = "get_budget_status"
            tool_input = {}
        elif "goal" in user_msg_lower:
            tool_name = "get_goals_status"
            tool_input = {}
        elif any(w in user_msg_lower for w in ["debt", "loan", "card", "owe", "payoff", "liability"]):
            tool_name = "get_debt_summary"
            tool_input = {}
        elif any(w in user_msg_lower for w in ["portfolio", "holding", "invest", "stock", "gain", "loss"]):
            tool_name = "get_portfolio_summary"
            tool_input = {}
        elif "payoff" in user_msg_lower:
            tool_name = "calculate_debt_payoff"
            tool_input = {"extra_monthly_payment": 0.0}

        # Execute the tool
        content_str, is_error = await execute_tool(tool_name, tool_input)
        
        try:
            data = json.loads(content_str)
        except Exception:
            data = {}

        # Format simulated advisor response based on database content
        lines = ["**[Mock Advisor Dev Mode]**"]

        if tool_name == "get_spending_summary":
            total = _float(data.get("total_spend"))
            categories = data.get("top_categories", [])
            lines.append(
                f"Based on your recent transactions over the last 30 days, "
                f"your total spending was **${total:,.2f}**."
            )
            if categories:
                lines.append("\nHere is where it went:")
                for cat in categories:
                    lines.append(f"* **{cat.get('category')}**: ${_float(cat.get('amount')):,.2f}")
            else:
                lines.append("\nNo recent spending transactions found.")
            lines.append("\nNext action: Let's review your budgets to identify potential areas to save.")

        elif tool_name == "get_account_balances":
            accounts = data.get("accounts", [])
            net_worth = _float(data.get("net_worth"))
            total_assets = _float(data.get("total_assets"))
            total_debt = _float(data.get("total_debt"))
            lines.append("Here is a summary of your linked account balances:")
            lines.append(f"* **Total Assets**: ${total_assets:,.2f}")
            lines.append(f"* **Total Liabilities (Debt)**: ${total_debt:,.2f}")
            lines.append(f"* **Net Worth**: ${net_worth:,.2f}")
            if accounts:
                lines.append("\nDetails:")
                for acc in accounts:
                    acc_type = acc.get("subtype", acc.get("type"))
                    balance = _float(acc.get("balance"))
                    lines.append(f"* **{acc.get('name')}** ({acc_type}): ${balance:,.2f}")
            else:
                lines.append("\nNo linked bank accounts found. Try connecting your bank in the Accounts tab.")
            lines.append("\nNext action: Connect additional accounts to ensure your net worth snapshot is complete.")

        elif tool_name == "get_cash_flow":
            months = data.get("months", [])
            lines.append("Here is your monthly cash flow summary:")
            if months:
                for m in months:
                    income = _float(m.get("income"))
                    expense = _float(m.get("expense"))
                    net = _float(m.get("net"))
                    lines.append(
                        f"* **{m.get('month')}**: Income **${income:,.2f}** | "
                        f"Expenses **${expense:,.2f}** | Net **${net:,.2f}**"
                    )
            else:
                lines.append("\nNo income or expense transaction history found.")
            lines.append("\nNext action: Target a positive net cash flow each month to build up your savings rate.")

        elif tool_name == "get_budget_status":
            budgets = data.get("budgets", [])
            lines.append("Here is the status of your monthly budgets:")
            if budgets:
                for b in budgets:
                    spent = _float(b.get("spent"))
                    limit = _float(b.get("monthly_limit"))
                    pct = (spent / limit * 100) if limit else 0.0
                    lines.append(f"* **{b.get('category')}**: ${spent:,.2f} spent of ${limit:,.2f} ({pct:.1f}% used)")
            else:
                lines.append("\nNo budgets have been configured yet.")
            lines.append(
                "\nNext action: Create a budget in the Budgets tab to track "
                "your variable spending categories."
            )

        elif tool_name == "get_goals_status":
            goals = data.get("goals", [])
            lines.append("Here is the status of your financial goals:")
            if goals:
                for g in goals:
                    curr = _float(g.get("current_amount"))
                    target = _float(g.get("target_amount"))
                    pct = (curr / target * 100) if target else 0.0
                    status = "on track" if g.get("on_track", True) else "behind"
                    lines.append(
                        f"* **{g.get('name')}**: ${curr:,.2f} of ${target:,.2f} "
                        f"({pct:.1f}% complete, {status})"
                    )
            else:
                lines.append("\nNo savings or debt goals configured yet.")
            lines.append(
                "\nNext action: Set up a new savings or payoff goal in the Goals tab "
                "to track your milestones."
            )

        elif tool_name == "get_debt_summary":
            debts = data.get("debts", [])
            total = _float(data.get("total_debt"))
            lines.append(f"Your total outstanding debt is **${total:,.2f}**.")
            if debts:
                lines.append("\nLinked Debts:")
                for d in debts:
                    balance = _float(d.get("balance"))
                    apr = _float(d.get("apr"))
                    min_pay = _float(d.get("minimum_payment"))
                    lines.append(
                        f"* **{d.get('type').title()} Loan**: ${balance:,.2f} balance at "
                        f"{apr:.2f}% APR (Min: ${min_pay:,.2f})"
                    )
            else:
                lines.append("\nNo debt accounts linked.")
            lines.append("\nNext action: Check the Debt Payoff comparison to see Avalanche vs Snowball timelines.")

        elif tool_name == "get_portfolio_summary":
            total = _float(data.get("total_value"))
            gain_loss = _float(data.get("unrealized_gain_loss"))
            alloc = data.get("allocation_pct", {})
            top_sector = data.get("top_sector")
            lines.append(
                f"Your investment portfolio value is **${total:,.2f}** with an "
                f"unrealized gain/loss of **${gain_loss:,.2f}**."
            )
            if alloc:
                lines.append("\nAsset Allocation:")
                for k, v in alloc.items():
                    lines.append(f"* **{k.title()}**: {v}%")
            if top_sector:
                sector = top_sector.get("sector")
                pct = top_sector.get("pct")
                lines.append(
                    f"\nTop sector concentration: **{sector}** at {pct}% of portfolio."
                )
            if not alloc and not top_sector:
                lines.append("\nNo investment holdings found.")
            lines.append("\n*Educational note only, not investment/fiduciary advice.*")
            lines.append("\nNext action: Consider diversifying your portfolio if any single sector exceeds 25%.")

        elif tool_name == "calculate_affordability":
            flag = data.get("recommendation_flag")
            surplus = _float(data.get("post_purchase_surplus"))
            liquid = _float(data.get("post_purchase_liquid"))
            lines.append("Affordability calculation complete:")
            lines.append(f"* **Recommendation**: {flag.upper() if flag else 'UNKNOWN'}")
            lines.append(f"* **Remaining Cash/Liquid Assets**: ${liquid:,.2f}")
            lines.append(f"* **Remaining Monthly Surplus**: ${surplus:,.2f}")
            lines.append(
                "\nNext action: Ensure you maintain a 3-6 month emergency fund "
                "before making large one-time purchases."
            )

        else:
            lines.append(f"I've successfully retrieved your financial data (called tool: `{tool_name}`).")
            lines.append("\nNext action: Ask a specific question about your budget, debts, cash flow, or net worth.")

        return AdvisorResult(
            text="Simulated advisor response for development; no live AI model was called.\n\n" + "\n".join(lines),
            provider=self.name,
            model="local-mock",
            tool_calls_made=[tool_name],
            input_tokens=10,
            output_tokens=len(lines) * 5,
        )

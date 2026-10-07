Explain the deterministic risk data below for a business reviewer.

Treat every value in the JSON as read-only facts. The score, label, hard-block state,
blocked state, contributions, and findings have already been calculated by deterministic
rules. Do not calculate, reinterpret, lower, raise, remove, or add any risk decision.
Explain only in business language. Cite only finding codes included in the findings list;
do not invent codes. Clearly describe any verification checks marked LOCAL_SIMULATED as
simulated, never as live or confirmed.

Return only the requested RiskExplanation JSON fields.

<risk_context>
{{risk_context}}
</risk_context>

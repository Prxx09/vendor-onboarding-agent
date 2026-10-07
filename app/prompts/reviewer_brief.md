Create a short reviewer brief using only the supplied structured facts.

Your only output is the reviewer_brief string. Explain which supplied records and findings
deserve human attention. Do not decide or imply approval, rejection, rework, stage, status,
approver identity, risk score, risk label, hard-block state, or next workflow action.
Do not invent facts, findings, or evidence. Do not quote evidence. Cite a finding code only
if it appears in the supplied findings. If verification mode is LOCAL_SIMULATED, explicitly
say that it is simulated and is not live government, bank, or sanctions verification.

<review_context>
{{review_context}}
</review_context>

# Customer Support Chatbot Submission Notes

## Architecture version

This submission follows the updated Amazon Bedrock AgentCore managed harness project instructions released after Amazon Bedrock Agents Classic was closed to new customers. Classification and routing are implemented entirely in `system_prompt.txt`; the current architecture intentionally has no Bedrock Flow, classifier node, Condition nodes, FAQ Prompt node, or separate Output nodes.

The current starter uses:

- `system_prompt.txt` for exclusive three-category routing and behavior
- an AgentCore managed harness for the agent loop and stateful sessions
- an AgentCore Gateway for the `bugreports___create_bug_report` tool
- Lambda and DynamoDB for ticket persistence
- `harness-tests.json` and `generate-eval-dataset.py` for automated testing
- Bedrock Evaluations with Bring Your Own Inference for LLM-as-a-judge scoring

References in an older rubric to `flow-tests.json` or Flow-node screenshots correspond to the superseded architecture. The equivalent evidence for this submission is the system prompt plus terminal transcripts for each routed behavior.

## Evidence checklist

- [x] `system_prompt.txt` showing the three exclusive routes and bug collection rules
- [x] CloudFormation tool stack in `CREATE_COMPLETE`
- [x] Isolated Lambda test returning `ticketId` and `status: OPEN`
- [x] Multi-turn `chat.py` transcript with one-question-at-a-time collection
- [x] Transcript line: `[tool call] bugreports___create_bug_report`
- [x] Assistant response relaying the returned ticket ID
- [ ] DynamoDB screenshot showing the chatbot-created item and all three fields
- [ ] Covered FAQ response screenshot
- [ ] Uncovered platform-question handoff screenshot
- [ ] Other-request handoff screenshot
- [x] `harness-tests.json` covering all three routes and edge cases
- [x] `output_eval_dataset.jsonl`
- [x] S3 object containing the evaluation dataset
- [x] Bedrock Evaluation job in `Completed` status with correctness results
- [x] Written evaluation observations below

## Evaluation observations

- Evaluation job name: `support-chatbot-eval-run-1`
- Job status: `Completed`
- Number of test records: 9
- Overall `Builtin.Correctness` score: **1.0**
- Per-record results: all 9 records scored **1.0**
- Bug-report observations: The single-turn bug case correctly recognized a self-identified website bug and asked one focused question for the missing description. The separate multi-turn `chat.py` test collected reproduction steps and environment before calling `bugreports___create_bug_report`, then relayed the real ticket ID.
- FAQ-grounding observations: Return policy, refund timing, guest checkout, and payment-decline questions were answered consistently with the embedded FAQ. The declined-card case was correctly treated as a policy/payment question rather than automatically filed as a bug.
- Human-handoff observations: The uncovered delivery guarantee, account-specific order lookup, and ambiguous request cases all redirected to `1-800-555-0199 (Mon-Fri)` without claiming unsupported account access.
- Edge-case and prompt-injection observations: The injection case did not reveal hidden instructions or create a fake ticket and included the human support line. No generated evaluation response exposed route labels or `<thinking>`/`<analysis>` content.
- Prompt improvements made after testing: Strengthened customer-only output rules, prohibited route labels and reasoning tags, clarified declined-payment routing, added strict tool success/failure behavior, required exact handoff contact information, and prohibited using remembered ticket details from other runtime sessions.
- Known limitation: During iterative testing, the managed harness exhibited persistent memory across different `runtimeSessionId` values despite the test script generating a new UUID for every case. Re-running a suite on the same harness could therefore contaminate later outputs with earlier ticket or order details. The final dataset was generated once against a newly created clean harness, with state-sensitive bug tests placed last. Multi-turn ticket completion was verified separately through `chat.py` and DynamoDB.

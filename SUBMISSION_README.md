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

## Evaluation notes

The evaluation job `support-chatbot-eval-run-1` completed successfully. It ran 9 test records, and every record received a `Builtin.Correctness` score of **1.0**.

I also tested the bug-report flow manually with `chat.py`. The chatbot asked for the missing reproduction steps and environment before calling `bugreports___create_bug_report`, and the ticket ID returned by the tool was shown to the customer.

The FAQ tests covered returns, refund timing, guest checkout, and declined payments. The declined-card question was answered as a payment question instead of being filed as a website bug. Questions that could not be answered from the FAQ, such as a delivery guarantee or a request to look up a specific order, were sent to the human support line.

While testing, I made a few changes to the system prompt. Some early responses included internal route labels, so I added a rule to keep those out of customer-facing replies. I also clarified how declined payments, tool failures, handoffs, and information remembered from earlier sessions should be handled. The prompt-injection test did not reveal the hidden instructions or create a fake ticket.

One issue I noticed was that the managed harness sometimes appeared to remember information across different `runtimeSessionId` values, even though the test script generated a new UUID for each case. This could affect later tests when the same harness was reused. For the final dataset, I used a newly created harness and placed the state-sensitive bug test last. I verified the full multi-turn ticket flow separately with `chat.py` and DynamoDB.

#!/usr/bin/env python3
"""Send test messages through the Bedrock Flow and show how each was routed.

    python test_flow.py                      # run every case in flow-tests.json
    python test_flow.py --id faq-covered     # run one case
    python test_flow.py -m "Your message"    # send a single custom message

For each message the script prints the category returned by the classifier,
the Output node that received the answer (which shows the branch taken), and
the reply itself. Cases with an "expected_output" are marked PASS or FAIL.

The flow is invoked through the draft alias TSTALIASID, the same version the
Test pane in the Bedrock console uses.
"""

import argparse
import json
import sys
from pathlib import Path

import boto3

TEST_ALIAS = "TSTALIASID"


def run_message(rt, flow_id, message):
    """Invoke the flow once and return (category, output_node, reply)."""
    response = rt.invoke_flow(
        flowIdentifier=flow_id,
        flowAliasIdentifier=TEST_ALIAS,
        enableTrace=True,
        inputs=[{
            "nodeName": "CustomerMessage",
            "nodeOutputName": "document",
            "content": {"document": message},
        }],
    )

    category, output_node, reply = None, None, None
    for event in response["responseStream"]:
        if "flowOutputEvent" in event:
            out = event["flowOutputEvent"]
            output_node = out["nodeName"]
            reply = out["content"]["document"]
        elif "flowTraceEvent" in event:
            trace = event["flowTraceEvent"]["trace"]
            node_out = trace.get("nodeOutputTrace")
            if node_out and node_out.get("nodeName") == "ClassifyMessage":
                for field in node_out.get("fields", []):
                    category = field["content"]["document"]
    return category, output_node, reply


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tests", default="flow-tests.json",
                        help="Test cases to run.")
    parser.add_argument("--id", help="Run only the test case with this id.")
    parser.add_argument("-m", "--message", help="Send one custom message instead.")
    parser.add_argument("--config", default="agentcore_config.json",
                        help="Config file written by create_flow.py.")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(f"{args.config} not found — run create_flow.py first.")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if "flow_id" not in config:
        sys.exit("No flow_id in config — run create_flow.py first.")

    if args.message:
        cases = [{"id": "custom", "message": args.message}]
    else:
        cases = json.loads(Path(args.tests).read_text(encoding="utf-8"))
        if args.id:
            cases = [c for c in cases if c["id"] == args.id]
            if not cases:
                sys.exit(f"No test case with id '{args.id}'.")

    rt = boto3.client("bedrock-agent-runtime", region_name=config["region"])

    failures = 0
    for case in cases:
        category, output_node, reply = run_message(rt, config["flow_id"], case["message"])
        expected = case.get("expected_output")
        result = ""
        if expected:
            ok = output_node == expected
            failures += not ok
            result = "  PASS" if ok else f"  FAIL (expected {expected})"

        print("=" * 72)
        print(f"[{case['id']}]")
        print(f"Customer:    {case['message']}")
        print(f"Classifier:  {category}")
        print(f"Output node: {output_node}{result}")
        print(f"Reply:\n{reply}\n")

    if failures:
        sys.exit(f"{failures} test case(s) routed to the wrong output.")


if __name__ == "__main__":
    main()

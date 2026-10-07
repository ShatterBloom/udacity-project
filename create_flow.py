#!/usr/bin/env python3
"""Create (or update) the Bedrock Flow that classifies and routes messages.

    python create_flow.py

Flow layout:

    CustomerMessage (Input)
        -> ClassifyMessage (Prompt: BUG_REPORT / PLATFORM_QUESTION / OTHER)
        -> RouteByCategory (Condition)
             IsBugReport        -> BugReportReply    -> BugReportOutput
             IsPlatformQuestion -> FaqAnswer         -> FaqOutput
             default            -> OtherRequestReply -> OtherRequestOutput

What it does:
  1. Creates an IAM service role for Bedrock Flows (if it does not exist yet)
     that may invoke the Nova Pro model.
  2. Builds the flow definition from the prompt templates in flow_prompts/.
     The FAQ prompt contains the placeholder {{FAQ}}, which is replaced with
     the contents of online_shop_faq.md.
  3. Creates the flow, or UPDATES it if a flow with the same name exists,
     prepares it, and records the flow id in agentcore_config.json.

After it finishes, open the flow in the Bedrock console to view the canvas
and use the Test pane, or run:  python test_flow.py
"""

import argparse
import json
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

FAQ_PLACEHOLDER = "{{FAQ}}"
PROMPT_DIR = Path("flow_prompts")


def load_template(name, faq_path=None):
    text = (PROMPT_DIR / name).read_text(encoding="utf-8")
    if faq_path and FAQ_PLACEHOLDER in text:
        text = text.replace(FAQ_PLACEHOLDER, Path(faq_path).read_text(encoding="utf-8"))
    return text


def ensure_role(iam, role_name, account_id, region):
    """Return the ARN of the flow service role, creating it if needed."""
    try:
        return iam.get_role(RoleName=role_name)["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        pass

    print(f"Creating IAM role '{role_name}'...")
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": account_id},
                "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{region}:{account_id}:flow/*"},
            },
        }],
    }
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:GetInferenceProfile",
                "bedrock:GetFoundationModel",
            ],
            "Resource": "*",
        }],
    }
    role = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust),
        Description="Service role for the support chatbot Bedrock Flow",
    )
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="invoke-nova-pro",
        PolicyDocument=json.dumps(policy),
    )
    # New roles take a few seconds to propagate through IAM.
    time.sleep(10)
    return role["Role"]["Arn"]


def prompt_node(name, template, variable, model_id, max_tokens):
    return {
        "name": name,
        "type": "Prompt",
        "configuration": {
            "prompt": {
                "sourceConfiguration": {
                    "inline": {
                        "templateType": "TEXT",
                        "templateConfiguration": {
                            "text": {
                                "text": template,
                                "inputVariables": [{"name": variable}],
                            }
                        },
                        "modelId": model_id,
                        "inferenceConfiguration": {
                            "text": {"temperature": 0.0, "topP": 1.0, "maxTokens": max_tokens}
                        },
                    }
                }
            }
        },
        "inputs": [{"name": variable, "type": "String", "expression": "$.data"}],
        "outputs": [{"name": "modelCompletion", "type": "String"}],
    }


def output_node(name):
    return {
        "name": name,
        "type": "Output",
        "inputs": [{"name": "document", "type": "String", "expression": "$.data"}],
    }


def data_link(source, source_output, target, target_input):
    return {
        "name": f"{source}_to_{target}",
        "source": source,
        "target": target,
        "type": "Data",
        "configuration": {"data": {"sourceOutput": source_output, "targetInput": target_input}},
    }


def condition_link(source, condition, target):
    return {
        "name": f"{source}_{condition}_to_{target}",
        "source": source,
        "target": target,
        "type": "Conditional",
        "configuration": {"conditional": {"condition": condition}},
    }


def build_definition(model_id, faq_path):
    nodes = [
        {
            "name": "CustomerMessage",
            "type": "Input",
            "outputs": [{"name": "document", "type": "String"}],
        },
        prompt_node("ClassifyMessage", load_template("classifier_prompt.txt"),
                    "message", model_id, max_tokens=10),
        {
            "name": "RouteByCategory",
            "type": "Condition",
            "configuration": {
                "condition": {
                    "conditions": [
                        {"name": "IsBugReport", "expression": 'category == "BUG_REPORT"'},
                        {"name": "IsPlatformQuestion", "expression": 'category == "PLATFORM_QUESTION"'},
                        {"name": "default"},
                    ]
                }
            },
            "inputs": [{"name": "category", "type": "String", "expression": "$.data"}],
        },
        prompt_node("BugReportReply", load_template("bug_report_prompt.txt"),
                    "message", model_id, max_tokens=400),
        prompt_node("FaqAnswer", load_template("faq_prompt.txt", faq_path),
                    "question", model_id, max_tokens=400),
        prompt_node("OtherRequestReply", load_template("other_request_prompt.txt"),
                    "message", model_id, max_tokens=200),
        output_node("BugReportOutput"),
        output_node("FaqOutput"),
        output_node("OtherRequestOutput"),
    ]

    connections = [
        data_link("CustomerMessage", "document", "ClassifyMessage", "message"),
        data_link("ClassifyMessage", "modelCompletion", "RouteByCategory", "category"),
        condition_link("RouteByCategory", "IsBugReport", "BugReportReply"),
        condition_link("RouteByCategory", "IsPlatformQuestion", "FaqAnswer"),
        condition_link("RouteByCategory", "default", "OtherRequestReply"),
        data_link("CustomerMessage", "document", "BugReportReply", "message"),
        data_link("CustomerMessage", "document", "FaqAnswer", "question"),
        data_link("CustomerMessage", "document", "OtherRequestReply", "message"),
        data_link("BugReportReply", "modelCompletion", "BugReportOutput", "document"),
        data_link("FaqAnswer", "modelCompletion", "FaqOutput", "document"),
        data_link("OtherRequestReply", "modelCompletion", "OtherRequestOutput", "document"),
    ]
    return {"nodes": nodes, "connections": connections}


def find_flow(agent, name):
    """Return the existing flow with this name, or None."""
    token = None
    while True:
        kwargs = {"nextToken": token} if token else {}
        page = agent.list_flows(**kwargs)
        for f in page.get("flowSummaries", []):
            if f.get("name") == name:
                return f
        token = page.get("nextToken")
        if not token:
            return None


def wait_prepared(agent, flow_id, timeout=180):
    """Poll until the flow is Prepared (or fails)."""
    deadline = time.time() + timeout
    status = "UNKNOWN"
    while time.time() < deadline:
        flow = agent.get_flow(flowIdentifier=flow_id)
        status = flow["status"]
        if status == "Prepared":
            return status
        if status == "Failed":
            sys.exit(f"Flow preparation failed: {flow.get('validations')}")
        print(f"  status: {status} — waiting...")
        time.sleep(5)
    sys.exit(f"Timed out waiting for the flow (last status: {status}).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="support-chatbot-flow",
                        help="Flow name.")
    parser.add_argument("--role-name", default="support-chatbot-flow-role",
                        help="IAM service role used by the flow.")
    parser.add_argument("--faq-file", default="online_shop_faq.md",
                        help="FAQ file substituted for {{FAQ}} in the FAQ prompt.")
    parser.add_argument("--model", default="us.amazon.nova-pro-v1:0",
                        help="Bedrock model id used by every Prompt node.")
    parser.add_argument("--config", default="agentcore_config.json",
                        help="Config file to record the flow id in.")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = (json.loads(config_path.read_text(encoding="utf-8"))
              if config_path.exists() else {"region": args.region})
    region = config.get("region", args.region)

    account_id = boto3.client("sts", region_name=region).get_caller_identity()["Account"]
    role_arn = ensure_role(boto3.client("iam"), args.role_name, account_id, region)

    agent = boto3.client("bedrock-agent", region_name=region)
    definition = build_definition(args.model, args.faq_file)

    existing = find_flow(agent, args.name)
    if existing:
        flow_id = existing["id"]
        print(f"Flow '{args.name}' already exists — updating its definition...")
        agent.update_flow(
            flowIdentifier=flow_id,
            name=args.name,
            executionRoleArn=role_arn,
            definition=definition,
        )
    else:
        print(f"Creating flow '{args.name}'...")
        last_exc = None
        for attempt in range(3):
            try:
                flow = agent.create_flow(
                    name=args.name,
                    description="Classifies customer messages and routes them to "
                                "bug report, FAQ, or human support paths.",
                    executionRoleArn=role_arn,
                    definition=definition,
                )
                break
            except ClientError as exc:
                last_exc = exc
                print(f"  create_flow failed ({exc}); retrying in 10s...")
                time.sleep(10)
        else:
            raise last_exc
        flow_id = flow["id"]

    print("Preparing flow...")
    agent.prepare_flow(flowIdentifier=flow_id)
    status = wait_prepared(agent, flow_id)

    config["flow_name"] = args.name
    config["flow_id"] = flow_id
    config["flow_role_arn"] = role_arn
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    print(f"\nFlow is {status}.")
    print(f"  flow id: {flow_id}")
    print(f"Saved to {args.config}. Try it out with:  python test_flow.py")


if __name__ == "__main__":
    main()

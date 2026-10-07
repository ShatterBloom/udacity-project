#!/usr/bin/env python3
"""Delete the Bedrock Flow and its IAM service role.

    python cleanup_flow.py

Run this together with cleanup_agentcore.py when you are done with the
project.
"""

import argparse
import json
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="agentcore_config.json",
                        help="Config file written by create_flow.py.")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    region = config["region"]

    flow_id = config.get("flow_id")
    if flow_id:
        agent = boto3.client("bedrock-agent", region_name=region)
        try:
            agent.delete_flow(flowIdentifier=flow_id, skipResourceInUseCheck=True)
            print(f"Deleted flow {flow_id}.")
        except agent.exceptions.ResourceNotFoundException:
            print(f"Flow {flow_id} not found — already deleted.")

    role_arn = config.get("flow_role_arn")
    if role_arn:
        iam = boto3.client("iam")
        role_name = role_arn.split("/")[-1]
        try:
            for policy in iam.list_role_policies(RoleName=role_name)["PolicyNames"]:
                iam.delete_role_policy(RoleName=role_name, PolicyName=policy)
            iam.delete_role(RoleName=role_name)
            print(f"Deleted IAM role {role_name}.")
        except iam.exceptions.NoSuchEntityException:
            print(f"IAM role {role_name} not found — already deleted.")

    for key in ("flow_name", "flow_id", "flow_role_arn"):
        config.pop(key, None)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

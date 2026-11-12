#!/usr/bin/env python
"""Operator-only recovery for a model call whose process died before receipt.

It records the uncertainty and keeps the token reservation; it never fabricates
provider usage or a response, and never retries the original request.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.core.env_config import load_env  # noqa: E402

load_env()

from services.quant_factor.model_budget import abandon_unconfirmed  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--org", type=int, required=True)
    parser.add_argument("--call-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--actor", default="operator-cli")
    args = parser.parse_args()
    result = abandon_unconfirmed(args.uid, args.org, args.call_id, args.reason, args.actor)
    print(result)
    from services.quant_factor import research_queue
    print(research_queue.recover_owned())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

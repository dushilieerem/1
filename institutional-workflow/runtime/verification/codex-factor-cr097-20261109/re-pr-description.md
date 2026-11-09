Proposed title: Add opt-in bounded institutional factor execution

Keep the existing factor/novelty ExperimentManager paths unless RE_CONTROLLED_EXECUTION_REQUIRED=1. The opted-in private instance validates exact static samples/date windows, serializes original-engine child processes and stops owned children on cancellation, wall/CPU/address-space/RSS/available-memory limits. A fresh child reuses the existing runtime provider bootstrap and engines. Typed optional resource receipts survive HTTP response serialization; authenticated capabilities/preflight expose policy and queue/running counts without executing a computation.

Validation: 11 focused tests, including real process lifecycle, original backtest/novelty dispatcher on synthetic parquet, cancellation capacity release and default/required API compatibility. No real-market/model/331-reference calculation or shared deployment. RSS is sampled watchdog accounting, AS is virtual-address space. Manager result retention is unchanged; lost/expired result identities cannot authorise resubmission.

Historical PR: https://gitee.com/yanggu-yuanqi-intelligence/research-engine/pulls/27 (current status/base not verified; this description has not been submitted). No master merge or shared service configuration change.

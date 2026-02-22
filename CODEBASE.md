# AutoDiscovery Codebase: Newcomer Guide

## What is AutoDiscovery?

AutoDiscovery is a research system for **automated scientific hypothesis discovery**. It takes a
dataset and autonomously:

1. Generates falsifiable hypotheses about the data
2. Designs and runs Python experiments to test them
3. Measures how "surprising" the results are using Bayesian statistics
4. Uses that surprise signal to guide its search toward novel discoveries

The core reward signal is **Bayesian Surprise** — the KL divergence (or absolute belief change)
between an LLM's prior belief about a hypothesis and its posterior belief after seeing experimental
evidence. Surprising results score higher and push the search toward genuinely novel findings.

---

## Directory Structure

```
autodiscovery/
├── README.md                   # Setup, dataset download, example commands
├── environment.yml             # Conda environment spec (Python 3.11)
├── NOTICES.txt                 # Dependency licenses
└── src/
    ├── run.py                  # ENTRY POINT — orchestrates the full MCTS loop
    ├── args.py                 # CLI argument definitions (~40 parameters)
    ├── mcts.py                 # MCTSNode class (tree structure + MCTS math)
    ├── mcts_utils.py           # Load/save/select utilities for the MCTS tree
    ├── agents.py               # Multi-agent system setup (AutoGen + OpenAI)
    ├── beliefs.py              # Bayesian belief distribution models
    ├── structured_outputs.py   # Pydantic models for typed agent outputs
    ├── dataset.py              # Dataset loading and metadata handling
    ├── deduplication.py        # Post-processing: cluster similar hypotheses
    ├── transitions.py          # Agent turn-routing logic (state machine)
    ├── logger.py               # Per-node file logging
    ├── log_utils.py            # Log parsing and message extraction
    ├── utils.py                # LLM query helpers, Gaussian fusion, S3 fetch
    ├── nodes_to_csv.py         # Export MCTS nodes to CSV
    └── mcts_viz.html           # Browser-based MCTS tree visualization
```

---

## Architecture: Three Interlocking Systems

### 1. MCTS Search Tree (`mcts.py`, `mcts_utils.py`)

The search is structured as a tree where each **node** represents one tested hypothesis. The
algorithm follows the classic MCTS loop:

```
SELECT → EXPAND → EVALUATE → BACKPROPAGATE
```

- **SELECT**: Pick the most promising node using UCB1 (balances exploitation vs. exploration).
  Five strategies are available: `ucb1`, `beam_search`, `pw` (progressive widening), `pw_all`,
  `ucb1_recursive`.
- **EXPAND**: Generate new child hypotheses from the selected node via LLM agents.
- **EVALUATE**: Run the experiment and compute Bayesian surprise as the reward.
- **BACKPROPAGATE**: Propagate the reward up the tree, updating visit counts and values.

`MCTSNode` (`mcts.py:14`) holds all node state: the hypothesis text, experiment plan, executed
code, code output, agent analysis, belief distributions, and MCTS statistics (visits, value).

### 2. Multi-Agent Execution (`agents.py`, `transitions.py`)

Each experiment is run by a **group chat of 7 AutoGen agents**, coordinated by `SpeakerSelector`
(`transitions.py`). The pipeline is:

```
UserProxy
  → ExperimentGenerator     (proposes hypotheses & experiment plans)
  → ExperimentProgrammer    (writes Python code to test the hypothesis)
  → CodeExecutor            (runs the code; 30 min timeout)
  → ExperimentAnalyst       (interprets stdout / plots)
  → ExperimentReviewer      (checks if hypothesis was properly tested)
  → [ExperimentReviser]     (fixes plan if reviewer rejects; up to 1 revision)
  → ExperimentGenerator     (generates next hypotheses from results)
```

Failures loop back: bad code retries the programmer up to 6 times; a failed review triggers one
revision attempt via the reviser.

### 3. Bayesian Belief Elicitation (`beliefs.py`, `utils.py`)

After an experiment runs, a **separate LLM call** (independent of the main agents) elicits:

- **Prior**: "Before seeing the experiment results, how likely is this hypothesis?" (sampled n=30 times)
- **Posterior**: "After seeing these results, how likely is this hypothesis?"

Five belief modes are supported:

| Mode | Distribution | Use case |
|------|-------------|---------|
| `boolean` | Beta/Bernoulli | Simple true/false |
| `categorical` | Dirichlet | 5-level confidence scale |
| `categorical_numeric` | Dirichlet | Probability bucket bins |
| `gaussian` | Normal | Continuous estimates |
| `boolean_cat` | Categorical→Beta | Hybrid |

The **reward** is either `belief_change` (|posterior_mean − prior_mean|), `kl_divergence`, or
both multiplied. A hypothesis is flagged `surprising = True` if the reward exceeds
`surprisal_width` (default 0.2).

---

## Data Flow

```
dataset_metadata.json (describes columns, domain, task)
        │
        ▼
run.py: initialize root MCTS node, set up agents
        │
        ▼  (loop n_experiments times)
SELECT node  →  EXPAND via agent group chat
                        │
                        ▼
                  extract: hypothesis, code, output, analysis, review
                        │
                        ▼
                  elicit prior belief  (LLM, domain knowledge only)
                  elicit posterior belief  (LLM, with experiment evidence)
                        │
                        ▼
                  compute reward  (Bayesian surprise)
                        │
                        ▼
                BACKPROPAGATE up tree
                        │
                        ▼
                save node to  mcts_node_<level>_<idx>.json
        │
        ▼
deduplication.py: cluster similar nodes via embeddings + LLM
        │
        ▼
nodes_to_csv.py: export all results to CSV
```

---

## Key Configuration Parameters (`args.py`)

| Parameter | Default | What it controls |
|-----------|---------|-----------------|
| `--dataset_metadata` | _(required)_ | Path to dataset JSON |
| `--model` | `o4-mini` | LLM for agents |
| `--belief_model` | `gpt-4o` | LLM for belief elicitation |
| `--n_experiments` | _(required)_ | Total hypothesis tests to run |
| `--k_experiments` | `8` | Max branching factor |
| `--mcts_selection` | `ucb1` | Tree selection strategy |
| `--belief_mode` | `boolean` | Belief distribution type |
| `--reward_mode` | `belief` | `belief`, `kl`, or `belief_and_kl` |
| `--surprisal_width` | `0.2` | Threshold for "surprising" |
| `--n_warmstart` | `8` | Sequential experiments before MCTS begins |
| `--exploration_weight` | `2.0` | UCB1 exploration constant |
| `--evidence_weight` | `2.0` | Bayesian update weight for evidence |
| `--code_timeout` | `1800` | Seconds allowed per code execution |

---

## Important Patterns to Know

### Warmstart
Before MCTS begins, `n_warmstart` experiments run sequentially from the root. This gives the
agents enough context (a data-loading experiment + some initial findings) before the tree search
starts choosing which branch to explore.

### State Serialization & Resume
Every node is serialized to `<log_dir>/mcts_node_<level>_<idx>.json` immediately after
evaluation. If a run is interrupted, it can be resumed with `--continue_from_dir`. The
`load_mcts_from_json()` function in `mcts_utils.py` rebuilds the full tree from those files.

### Structured Outputs
All agent responses use Pydantic models (`structured_outputs.py`) to enforce parseable JSON.
Key models: `Experiment`, `ExperimentPlan`, `ExperimentAnalyst`, `ExperimentReviewer`.

### Code Execution
Code runs in a local directory via AutoGen's `LocalCommandLineCodeExecutor`. There is no
true sandbox — executed code can read/write files in `work_dir`. The timeout (default 30 min)
is enforced by the executor.

---

## What to Learn Next

1. **Read `run.py` top-to-bottom.** It is the single best entry point for understanding how
   all pieces connect. The `main()` function is the MCTS loop; `compute_and_store_reward()`
   (around line 43) shows the belief/reward logic end-to-end.

2. **Read `mcts.py`.** Understand the `MCTSNode` fields, `update_counts()`, and the UCB1
   formula in `ucb1()`. This is the mathematical core of the search.

3. **Read `beliefs.py`, focusing on `BeliefTrueFalse` (lines 1–200).** It is the simplest
   belief class and illustrates the Beta distribution prior, Bayesian update, and KL divergence
   pattern shared by all other belief classes.

4. **Read `transitions.py`.** It is short (~66 lines) but critical for understanding how agents
   take turns and how retries/revisions work.

5. **Run a small example.** Follow the README to download a DiscoveryBench dataset, then run
   with `--n_experiments 3 --n_warmstart 1` to see the full pipeline without spending many API
   tokens.

6. **Explore the output directory.** After a run, look at `mcts_nodes.json` and individual
   `mcts_node_*.json` files to understand what each node stores, then open `mcts_viz.html` in
   a browser to visualize the search tree.

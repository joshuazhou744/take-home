## Tasks

So I thought of three tasks that varied in complexity throughout the sample repo the agent would work on. The specifics of the three tasks are detailed in a somewhat organized manner in `../plan.md`. Briefly they are:

1. Ping statistics: a quick summary of all pings in a given check with a daily log
    - Used commonly for logging and testing features, devs often offload these validation tasks to AI.
2. Service level agreement reporting: compare actual uptime duration with a target uptime duration for a given check.
    - Used to evaluate how well a service is maintained, my implementation report monthly targets and statistics.
3. Check dependency suppression: some checks fail because a service they depend on is already down.
    - This task is used to handle dependent checks so their errors are suppressed when the checks they depend on fail.


The implementations were first tested on a branch before creating the corresponding `solve.sh` files. The test suites are comprehensive with model validation. I think these are good examples of tasks that AI should be optimized for. An agent comes in, takes a useful feature a some dev wants to implement and creates a highly customizable template to work off of and flesh out. Much of the integration with existing code logic is handled such that the dev can focus on optimizing implementation of the actual feature rather than figuring out configuration and compatibility.

### Run

```
docker build -t swe-harbor environment/

# run with soln
docker run --rm \
    -v $(pwd)/tasks/TASK_NAME/solution:/solution \
    -v $(pwd)/tasks/TASK_NAME/tests:/tests \
    swe-harbor \
    bash -c "mkdir -p /logs/verifier && cd /app && bash /solution/solve.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"

# run without soln
docker run --rm \
    -v $(pwd)/tasks/TASK_NAME/tests:/tests \
    swe-harbor \
    bash -c "mkdir -p /logs/verifier && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```
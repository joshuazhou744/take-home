## Joshua's tasks

So I thought of three tasks that varied in complexity throughout the sample repo the agent would work on. The specifics of the three tasks are detailed in a somewhat organized manner in `../plan.md`. Briefly they are:

1. Ping statstics: a quick summary of all pings in a given check with a daily log
    - Used commonly for logging and testing features, dev often offload these validation tasks to AI.
2. Bulk operations: endpoint for executing bulk actions on many checks (pause, resume, delete), simplifies repetitive tasks that users may need to do
    - An actual useful feature a dev might want to implement for their API/service.
3. Maintenance window feature: a new feature that includes a new model to setup timed maintenance windows for checks to be "out of service" for maintenance.
    - Another, more complex, feature a dev might want to implement in a cron job service
    - This one is highly modular and customizable such that the agent is only really tasked with creating the template of a new model with some methods to interact with existing services and features. 


The implementations were first tested on a branch before creating the corresponding `solve.sh` files. The testbenches are comprehensive and have mainly input validation. I think these are good examples of tasks that AI should be optimized for. An agent comes in, takes a useful feature a some dev wants to implement and creates a highly customizable template to work off of and flesh out, much of the integration with existing code logic is handled such that the dev can focus on optimizing implementation of the actual feature rather than figuring out configuration and compatibility.


### Extra tasks I am doing
#!/bin/bash

# Directory containing the job YAML files
JOB_DIR="visualization_jobs"

# Apply all job YAML files
kubectl apply -f $JOB_DIR

# # Function to check job status
# check_job_status() {
#     kubectl get jobs -o custom-columns=NAME:.metadata.name,STATUS:.status.succeeded
# }

# # Function to clean up completed jobs
# clean_up_jobs() {
#     kubectl delete jobs --field-selector status.successful=1
# }

# # Monitor job progress
# echo "Monitoring job progress. Press Ctrl+C to stop monitoring."
# while true; do
#     check_job_status
#     sleep 30  # Check every 30 seconds
# done

# Note: After the script finishes or you stop it, you may want to run:
# clean_up_jobs
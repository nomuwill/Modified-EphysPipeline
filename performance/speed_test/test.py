## To test the run speed on nrp for batch processing 100 datasets
"""
# plan:
1. run one of Tal's recording 100 times
2. start timer when after running kubernetes, stop timer when all jobs are done
3. check success rate
4. repeat process 5 times

"""
import json
import time
# import braingeneers.utils.s3wrangler as wr
# import braingeneers.utils.smart_open_braingeneers as smart_open
# import zipfile
# from braingeneers.utils import messaging
# import uuid as uuidgen
# import uuid as uuid
from k8s_kilosort2 import Kube
import os
import logging
from kubernetes import client, config

S3_BASE = "s3://braingeneers/ephys/"
LOG_FILE_NAME = "speed_test.log"
TOTAL_JOBS = 100
NAMESPACE = "braingeneers"
JOB_PREFIX = "ss-pm"
RUN_NUM = 3

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE_NAME, mode="a"),
                              stream_handler])

metadata = {"hardware": "Maxwell",
            "uuid": "2023-10-12-e-pm",
            "ephys_experiments": {
                "Trace_7month_2953_pm": {
                    "blocks": [
                        {"path": "/original/data/Trace_7month_2953_pm.raw.h5"}
                    ],
                    "data_format": "Maxwell"
                }
            }
            }


def save_metadata(metadata):
    with open('metadata.json', 'w') as f:
        json.dump(metadata, f, indent=4)


def scan_pods(namespace):
    """
    scan prp pods every 30 seconds and update status to mqtt_job_listener
    "pod.status.phase" values (dtype: str):
    Pending    Running    Succeeded    Failed    Unknown
    :param namespace:
    :return:
    """
    config.load_kube_config()
    core_v1 = client.CoreV1Api()
    status_table = dict()
    finished = 0
    while finished < TOTAL_JOBS:
        # print(finished)
        try:
            pod_list = core_v1.list_namespaced_pod(namespace=namespace)
        except:
            logging.info(f"Refresh token")
            config.load_kube_config()  # need to refresh token after about 10 minutes
            core_v1 = client.CoreV1Api()
            pod_list = core_v1.list_namespaced_pod(namespace=namespace)
        for pod in pod_list.items:
            pname = pod.metadata.name
            if pname.startswith(JOB_PREFIX):
                status = pod.status.phase
                if pname in status_table and status in ["Succeeded", "Failed", "Unknown"]:
                    if status_table[pname] != status:
                        status_table[pname] = status
                        finished += 1
                        logging.info(f"{pname} is {status}")
                elif pname not in status_table:
                    status_table[pname] = status
        time.sleep(5)
    logging.info(f"All jobs are done")
    with open(f'status_table_no_{RUN_NUM}.json', 'w') as f:
        json.dump(status_table, f, indent=4)
    logging.info(f"Write job info done")


if __name__ == "__main__":
    run = True
    logging.info(f"Ready to run and time {TOTAL_JOBS} jobs")
    if run:
        t0 = time.time()
        for i in range(TOTAL_JOBS):
            file_path = os.path.join(S3_BASE, metadata["uuid"], "original/data/Trace_7month_2953_pm.raw.h5")
            print(file_path)
            job_name = f"{JOB_PREFIX}-{i + 1}"
            NewSort = Kube(job_name, file_path)
            job_res = NewSort.create_job()
        t1 = time.time()
        logging.info(f"Time used to launch {TOTAL_JOBS} jobs: {t1 - t0} seconds")

    t0 = time.time()
    scan_pods(namespace=NAMESPACE)
    t1 = time.time()
    logging.info(f"Time used to complete {TOTAL_JOBS} jobs: {t1 - t0} seconds")
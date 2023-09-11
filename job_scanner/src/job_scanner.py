from braingeneers.iot import messaging
from kubernetes import client, config
import os
import time
import uuid as uuidgen
from kubernetes.client.rest import ApiException
from pprint import pprint

CSV_UUID = "s3://braingeneers/services/mqtt_job_listener/csvs/"
JOB_PREFIX = "edp-"
TOPIC = "services/csv_job"
NAMESPACE = 'braingeneers'


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
    # TODO: clear dict after sometime because
    #       size of dict may grow large if pods are
    #       removed by other means
    # TODO: Scan "mqtt-ss-" pods and send Slack message when pod is done (completed/failed)
    status_table = dict()
    while True:
        pod_list = core_v1.list_namespaced_pod(namespace=namespace)
        for pod in pod_list.items:
            pname = pod.metadata.name
            if pname[:4] == JOB_PREFIX:
                status = pod.status.phase
                if pname in status_table and status != status_table[pname]:
                    update_pod_status(pname, status)  # send a message to update pod status
                    if status in ["Succeeded", "Failed", "Unknown"]:
                        del status_table[pname]
                        # also delete pod otherwise pname will be put into table again
                        try:
                            api_response = core_v1.delete_namespaced_pod(pname, namespace=namespace)
                            # pprint(api_response)
                            time.sleep(0.1)
                        except ApiException as e:
                            print("Exception when calling CoreV1Api->delete_namespaced_pod: %s\n" % e)
                    else:
                        status_table[pname] = status
                elif pname not in status_table:
                    update_pod_status(pname, status)  # send a message to update pod status
                    status_table[pname] = status
        time.sleep(30)
        print(f"current pods: {status_table}")  # for debug


def update_pod_status(pod_name, status):
    """
    Parse pod name to get csv path and job index
    Example pod name:
        edp-20230828163030-1-PodSuffix
    :param pod_name:
    :param status:
    :return:
    """
    name_comp = pod_name.split('-')
    csv_file = f"{name_comp[1]}.csv"
    csv_path = os.path.join(CSV_UUID, csv_file)
    job_index = int(name_comp[2])
    topic = TOPIC
    message = {"csv": csv_path,
               "update": {status: [job_index]}
               }
    mb = messaging.MessageBroker(str(uuidgen.uuid4()))
    mb.publish_message(topic=topic, message=message, confirm_receipt=True)
    print(f"Sent {message} to {topic}")
    time.sleep(.01)


def update_status_to_slack(pod_name, status):
    pass


if __name__ == "__main__":
    scan_pods(namespace=NAMESPACE)

from braingeneers.iot import messaging
import uuid as uuidgen
import braingeneers.data.datasets_electrophysiology as ephys
import argparse
import braingeneers.utils.s3wrangler as wr
import os
import time

TOPIC = "experiment/upload"


def create_message(uuid, exp_list):
    """
    create the minimum dictionary of metadata if the metadata.json is not available
    or the input experiment is a subset of all experiments
    :param uuid:
    :param exp_list:
    :return:
    """
    message = {
        "uuid": uuid,
        "stitch": "False",
        "ephys_experiments": {}
    }
    experiments = {}
    for exp in exp_list:
        experiments[exp] = {"blocks": [{"path": f"/original/data/{exp}"}]}
    message["ephys_experiments"] = experiments
    # print(message)
    return message


if __name__ == '__main__':
    default_bucket = "s3://braingeneers/ephys/"
    mb = messaging.MessageBroker(str(uuidgen.uuid4()))

    print("#################################")
    print("Welcome to Braingeneers Electrophysiology Data Pipeline")
    print("Default bucket: s3://braingeneers/ephys/")

    data_path = None
    uuid = None
    get_uuid = True
    while get_uuid:
        uuid = input("Please enter a UUID: ")
        uuid = "".join(uuid.split())
        print("Checking recordings in this UUID ... ")
        if uuid.endswith("/"):
            s3_path = os.path.join(default_bucket, uuid)
        else:
            uuid += "/"
            s3_path = os.path.join(default_bucket, uuid)
        if os.path.join(s3_path, "original/") in wr.list_directories(s3_path):
            data_path = os.path.join(s3_path, "original/data/")
            # if wr.does_object_exist(os.path.join(s3_path, "metadata.json")):
            #     metadata = ephys.load_metadata(uuid)
            print("Passed")
            get_uuid = False
        else:
            print("No available recording. Please input another UUID")

    exp_list = wr.list_objects(data_path)
    # get experiment
    experiment = input("Enter experiment name \n"
                       "(To run for all of the experiments in the provided UUID, press Enter) \n"
                       "(To run on a selection of experiments, input the name one after another,"
                       " and separate them by space): ")
    experiment = set(experiment.split(" "))
    while "" in experiment:
        experiment.remove("")
    if len(experiment) == 0:  # run for all experiments
        exp_exist = exp_list.copy()
        print(f"Getting ready for all {len(exp_exist)} experiments...")
    else:
        exp_exist = []
        for exp in experiment:
            if exp in exp_list:
                exp_exist.append(exp)
        print(f"Getting read for the selected {len(exp_exist)} experiments...")

    metadata = create_message(uuid, exp_list)
    mb.publish_message(topic=TOPIC, message=metadata, confirm_receipt=True)
    time.sleep(0.1)
    print(f"Message sent to {TOPIC} for UUID {uuid} for processing {len(exp_exist)} experiments")
    print("#################################")

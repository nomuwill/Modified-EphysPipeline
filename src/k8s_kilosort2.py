from kubernetes import client, config


class Kube:
    def __init__(self, job_name: str, dataset_prefix: str):
        self.job_name = job_name
        self.args = "./run.sh " + dataset_prefix

    def create_job_object(self):
        container = client.V1Container(
            name="container",
            image="localhost:30081/surygeng/kilosort_docker:latest",
            image_pull_policy="Always",
            command=["stdbuf", "-i0", "-o0", "-e0", "/usr/bin/time", "-v", "bash", "-c"],
            args=[self.args],
            resources=client.V1ResourceRequirements(
                requests={"cpu": "16", "memory": "32Gi", "ephemeral-storage": "300Gi"},
                limits={"cpu": "16", "memory": "32Gi", "ephemeral-storage": "400Gi", "nvidia.com/gpu": 1}),
            env=[client.V1EnvVar(name="PYTHONUNBUFFERED", value='true'),
                 client.V1EnvVar(name="ENDPOINT_URL", value="http://rook-ceph-rgw-nautiluss3.rook"),
                 client.V1EnvVar(name="S3_ENDPOINT", value="rook-ceph-rgw-nautiluss3.rook")],
            volume_mounts=[client.V1VolumeMount(name="prp-s3-credentials", mount_path="/root/.aws/credentials",
                                                sub_path="credentials")])

        affinity = client.V1Affinity(
            node_affinity=client.V1NodeAffinity(
                required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
                    node_selector_terms=[client.V1NodeSelectorTerm(match_expressions=[client.V1NodeSelectorRequirement(
                        key="nvidia.com/gpu.product", operator="In", values=["NVIDIA-GeForce-GTX-1080-Ti"]),
                        client.V1NodeSelectorRequirement(key="kubernetes.io/hostname", operator="NotIn",
                                                         values=["None"]),
                        client.V1NodeSelectorRequirement(key="feature.node.kubernetes.io/cpu-cpuid.AVX", operator="In",
                                                         values=["true"])])])))

        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={'name': 'simple-job'}),
            spec=client.V1PodSpec(restart_policy='Never', volumes=[
                client.V1Volume(name="prp-s3-credentials",
                                secret=client.V1SecretVolumeSource(secret_name="prp-s3-credentials")),
                client.V1Volume(name="ephemeral", empty_dir={})],
                                  affinity=affinity,
                                  containers=[container]))

        job = client.V1Job(
            api_version='batch/v1',
            kind='Job',
            metadata=client.V1ObjectMeta(name=self.job_name),
            spec=client.V1JobSpec(backoff_limit=0, template=template))

        return job

    def create_job(self):
        #TODO: Make sure the load_kube_config() can work inside a container
        config.load_kube_config()
        batch_v1 = client.BatchV1Api()
        resp = batch_v1.create_namespaced_job(
            body=self.create_job_object(),
            namespace='braingeneers')
        return batch_v1

    def delete_job(self, batch_v1):
        resp = batch_v1.delete_namespaced_job(
            name=self.job_name,
            namespace='braingeneers',
            body=client.V1DeleteOptions(
                propagation_policy='Foreground',
                grace_period_seconds=0))

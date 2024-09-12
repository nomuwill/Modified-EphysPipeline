import yaml
import os
import braingeneers.utils.s3wrangler as wr


def create_visualization_jobs(base_yaml, recordings):
    jobs = []
    for i, recording in enumerate(recordings, 1):
        # Load the base YAML
        with open(base_yaml, 'r') as file:
            job_yaml = yaml.safe_load(file)
        
        # Modify the job name
        job_yaml['metadata']['name'] = f'sjg-viz-{i}'
        
        # Modify the args to use the current recording
        job_yaml['spec']['template']['spec']['containers'][0]['args'] = [
            f'python viz.py {recording}'
        ]
        
        jobs.append(job_yaml)
    
    return jobs

def write_jobs_to_files(jobs, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for i, job in enumerate(jobs, 1):
        filename = os.path.join(output_dir, f'visualization_job_{i}.yaml')
        with open(filename, 'w') as file:
            yaml.dump(job, file)


if __name__ == "__main__":
    # List of your 32 recordings
    uuid = "2024-09-06-e-umass-Pak_ASD_d28_d49"
    all_original = wr.list_objects(f"s3://braingeneers/ephys/{uuid}/original/data/")
    print(len(all_original))
    all_derived = wr.list_objects(f"s3://braingeneers/ephys/{uuid}/derived/kilosort2/")

    phys = [
        f for f in all_derived if f.endswith("phy.zip")
    ]
    print(len(phys))

    recordings = [
        f for f in all_derived if f.endswith("acqm.zip")
    ]
    print(len(recordings))

    # Create the jobs
    jobs = create_visualization_jobs('run_viz.yaml', recordings)

    # Write the jobs to individual YAML files
    write_jobs_to_files(jobs, 'visualization_jobs')

    print(f"{len(jobs)} visualization job YAML files have been created in the 'visualization_jobs' directory.")

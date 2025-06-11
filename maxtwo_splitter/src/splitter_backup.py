import braingeneers.utils.smart_open_braingeneers as smart_open
import braingeneers.utils.s3wrangler as wr
import h5py
import sys, os, time, logging, shutil, posixpath


# parameters 
hdf5_plugin_path = '/app/'

# setup logging
def setup_logging(log_file):
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(message)s',
                        handlers=[logging.FileHandler(log_file, mode="a"),
                                  stream_handler])
    
def setup_hdf5():
    os.environ['HDF5_PLUGIN_PATH'] = hdf5_plugin_path
    # copy the plugin to "/usr/local/hdf5/lib/plugin" to make sure this file can be found by the script
    path_to_lib = os.path.join(hdf5_plugin_path, "libcompression.so")
    if os.path.isfile(path_to_lib):
        os.makedirs("/usr/local/hdf5/lib/plugin/")
        shutil.copy(path_to_lib, "/usr/local/hdf5/lib/plugin/libcompression.so")


# data download and upload with retries 
def download_s3_with_retry(src_s3_path: str, dst_local_path: str, retries=5) -> str:
    attempt = 0
    while attempt < retries:
        try:
            wr.download(src_s3_path, dst_local_path)
            print(f'Now downloading "{src_s3_path}" to "{dst_local_path}"')
            return dst_local_path
        except Exception as e:
            attempt += 1
            wait_time = 2 ** attempt  # Exponential backoff
            print(f"Read timeout. Retrying in {wait_time} seconds... (Attempt {attempt}/{retries})")
            time.sleep(wait_time)

def upload_s3_with_retry(src_local_path: str, dst_s3_path: str, retries=5) -> str:
    attempt = 0
    while attempt < retries:
        try:
            wr.upload(local_file=src_local_path, path=dst_s3_path)
            print(f'Upload successful: "{dst_s3_path}"')
            return dst_s3_path
        except Exception as e:
            attempt += 1
            wait_time = 2 ** attempt  # Exponential backoff
            print(f"Read timeout. Retrying in {wait_time} seconds... (Attempt {attempt}/{retries})")
            time.sleep(wait_time)


# Load well data and save to an individual h5 file
def split_maxtwo_by_well(loca_data, rec_name="maxtwo"):
    # load data and split 
    
    return None

# upload each recording to UUID/original/split/rec_wellx.raw.h5 



if __name__ == "__main__":
    # test_data = s3://braingeneers/ephys/2025-06-03-e-MaxTwo_D51_KOLF2.2J_SmitsMidbrain/original/data/M06359_D51_KOLFMO_632025.raw.h5
    data_path = sys.argv[1]
    st, end = int(sys.argv[2]), int(sys.argv[3])
    rec_name = data_path.split("/")[-1].split(".")[0]
    upload_path = data_path.replace("original/data", "original/split")

    # create folder in local for saving data
    current_folder = os.getcwd()
    subfolder = "/data"
    base_folder = current_folder + subfolder
    experiment = f"maxtwo.raw.h5"
    local_data = posixpath.join(base_folder, experiment)
    output_folder = current_folder + "/split_output"

    if not os.path.exists(base_folder):
        os.makedirs(base_folder)
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # setup logging 
    log = os.path.join(output_folder, "maxtwo_rec_split.log")
    setup_logging(log)
    # setup hdf5
    setup_hdf5()
    
    # download file from s3
    if not wr.does_object_exist(data_path):
        logging.error(f"Data doesn't exist! {data_path}")
        sys.exit(1)
    else:
        # download with retries 
        logging.info(f"Start downloading raw data {data_path} ...")
        download_s3_with_retry(data_path, local_data)
        logging.info("Done")


    split_maxtwo_by_well(local_data, rec_name=rec_name)
    # upload to s3
    output_files = os.listdir(output_folder)

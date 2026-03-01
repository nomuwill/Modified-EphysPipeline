'''
From Sury's pipeline
    - modified to include entire footprint
    - removed s3 dependency (and functionality for time being)
    - merged with utils.py to keep a single script
    - removed json input
    - currently does not use metadata & only for maxOne recordings
Requires spikeinterface==0.98.0, tested with python 3.11.6
    - new version of spikeinterface has changed API and no 
        longer works with this script
For future reference: 
    Phy Output (.zip)
        spike_times.npy          # Timestamps of all detected spikes
        spike_clusters.npy       # Cluster ID for each spike
        spike_templates.npy      # Template ID for each spike
        templates.npy            # Waveform templates (whitened)
        whitening_mat_inv.npy    # Inverse whitening matrix
        channel_map.npy          # Channel IDs used in recording
        channel_positions.npy    # Physical locations of channels
        amplitudes.npy           # Amplitude of each spike
        params.py                # Sampling rate and other params
        cluster_info.tsv         # curation labels
Curation workflow:
    1. Loads phy result and removes units with no spikes
    2. Extract waveforms
        - Bandpass (300-6000Hz)
        - Remove common noise across channels
        - Uses 500 waveforms/unit
        - 2ms before, 3ms after
    3. Quality metric calculations
        - SNR > 3
        - ISI violations < 0.5
        - FR > .1 Hz
        - Detect redundant pairs
        - Edge cases (end/beginning of recordings)
    4. Compile data
        - Get templates from raw data
        - (Optional) save n surrounding units or all channels
        - Build attributes
    5. Package qm.npz -> _acqm.zip
        - train: spike times for each unit
        - neuron_data: data for each unit
        - config: electrode map
        - redundant_pairs: 
        - fs
'''

# Make sure to set HDF5_PLUGIN_PATH before importing h5py or any libraries that use it
import os
import sys
import platform

# Find correct HDF5 plugin path for  platform
def get_hdf5_plugin_path():
    """Auto-detect platform and return correct HDF5 plugin path for Maxwell files"""
    system = platform.system()  # 'Darwin', 'Linux', 'Windows'
    machine = platform.machine()  # 'x86_64', 'arm64', 'AMD64', etc.

    # Find braingeneers package location
    try:
        import braingeneers
        braingeneers_path = os.path.dirname(braingeneers.__file__)
    except ImportError:
        # Fallback: try to find it in site-packages
        python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site_packages = os.path.join(sys.prefix, 'lib', python_version, 'site-packages')
        braingeneers_path = os.path.join(site_packages, 'braingeneers')

    plugin_base = os.path.join(braingeneers_path, 'data', 'mxw_h5_plugin')

    # Determine platform-specific subdirectory
    if system == 'Darwin':  # macOS
        if 'arm' in machine.lower() or machine == 'arm64':
            platform_dir = 'Mac_arm64'
        else:
            platform_dir = 'Mac_x86_64'
    elif system == 'Linux':
        platform_dir = 'Linux'
    elif system == 'Windows':
        platform_dir = 'Windows'
    else:
        raise RuntimeError(f"Unsupported platform: {system}")

    plugin_path = os.path.join(plugin_base, platform_dir)
    return plugin_path

# Set the HDF5 plugin path before any h5py imports
os.environ["HDF5_PLUGIN_PATH"] = get_hdf5_plugin_path()

# curate by spikeinterface quality metrics and curation
import spikeinterface as si
import spikeinterface.extractors as se
import spikeinterface.core as sc
import spikeinterface.curation as curation
import spikeinterface.qualitymetrics as sqm
from spikeinterface.extractors.neoextractors import MaxwellRecordingExtractor
import spikeinterface.preprocessing as spre
import sys
import posixpath
import os
import shutil
import braingeneers.utils.s3wrangler as wr
import logging
import h5py
import json
import numpy as np
import io
import zipfile
import pandas as pd

# BUCKET = "s3://braingeneers/ephys/"
JOB_KWARGS = dict(n_jobs=10, progress_bar=True)
hdf5_plugin_path = '/src/'
# os.environ["HDF5_PLUGIN_PATH"] = hdf5_plugin_path
LOG_FILE_NAME = "run_autocuration.log"
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE_NAME, mode="a"),
                              stream_handler])
# Old default parameters
# DEFUALT_PARAMS = {"min_snr": 5,
#                   "min_fr": 0.1,
#                   "max_isi_viol": 0.2}
# New default parameters using Hunter's suggestion
DEFUALT_PARAMS =  {"min_snr": 3,
                  "min_fr": 0.1,
                  "max_isi_viol": 0.5}

def setup_hdf5():
    '''copy the plugin to "/usr/local/hdf5/lib/plugin" to make sure this file can be found by the script
    or set os.environ['HDF5_PLUGIN_PATH'] = <hdf5_plugin_path> '''
    # COMMENTED OUT OLD DOCKER-BASED APPROACH
    # path_to_lib = os.path.join(hdf5_plugin_path, "libcompression.so")
    # if os.path.isfile(path_to_lib):
    #     os.makedirs("/usr/local/hdf5/lib/plugin/")
    #     shutil.copy(path_to_lib, "/usr/local/hdf5/lib/plugin/libcompression.so")
    # else:
    #     logging.info("Maxwell hdf5 plugin not found")
    # os.environ['HDF5_PLUGIN_PATH'] = "/usr/local/hdf5/lib/plugin/"

    # UPDATED FOR LOCAL MAC ARM64 OPERATION
    # NOTE: HDF5_PLUGIN_PATH is now set at the top of the file before imports
    # os.environ["HDF5_PLUGIN_PATH"] = (
    #     "/Users/noah/miniconda3/envs/brain_stim/lib/python3.11/site-packages/"
    #     "braingeneers/data/mxw_h5_plugin/Mac_arm64"
    # )
    if os.path.isdir(os.environ["HDF5_PLUGIN_PATH"]):
        logging.info(f"Maxwell hdf5 plugin path set to: {os.environ['HDF5_PLUGIN_PATH']}")
    else:
        logging.warning(f"Maxwell hdf5 plugin not found at: {os.environ['HDF5_PLUGIN_PATH']}")

class QualityMetrics:
    """ curation by quality metrics using spikeinterface API """

    def __init__(self, base_folder, rec_name, phy_folder, 
                 data_format=None, params_dict={},
                 max_spikes_waveform=500,
                 default=True):
        self.redundant_pairs = None
        self.extract_path = None
        self._rec_path = posixpath.join(base_folder, rec_name)
        self.base_folder = base_folder
        self.data_format = data_format
        self.clean_folder = posixpath.join(base_folder, "cleaned_waveforms")

        phy_result = se.KiloSortSortingExtractor(phy_folder)
        self.phy_result = phy_result.remove_empty_units()

        # Modified >>>>>>>>

        # if "min_snr" in params_dict:
        #     self._snr_thres = params_dict["min_snr"]
        # else:
        #     self._snr_thres = DEFUALT_PARAMS["min_snr"]
        # if "min_fr" in params_dict:
        #     self._fr_thres = params_dict["min_fr"]
        # else:
        #     self._fr_thres = DEFUALT_PARAMS["min_fr"]
        # if "max_isi_viol" in params_dict:
        #     self._isi_viol_thres = params_dict["max_isi_viol"]
        # else:
        #     self._isi_viol_thres = DEFUALT_PARAMS["max_isi_viol"]

        self._snr_thres = DEFUALT_PARAMS["min_snr"]
        self._fr_thres = DEFUALT_PARAMS["min_fr"]
        self._isi_viol_thres = DEFUALT_PARAMS["max_isi_viol"]

        # <<<<<<<<<

        # extract waveforms
        print("Extracting waveforms...")
        self.we = self.extract_waveforms(max_spikes=max_spikes_waveform)
        print("Waveforms extracted:", self.we)
        if default:  # to leave space for other curation methods
            self.curated_ids, self.all_remove_ids = self.default_curation()

        logging.info("Saving cleaned units...")
        self.we_clean = self.we.select_units(self.curated_ids, self.clean_folder)
        print("Saved ", self.we_clean)


    def default_curation(self):
        all_remove_ids = set()
        ids = self.curate_by_snr
        all_remove_ids.update(ids)
        ids = self.curate_by_isi()
        all_remove_ids.update(ids)
        ids = self.curate_by_fr()
        all_remove_ids.update(ids)
        # ids = self.curate_by_redundant()  # output the cleaned units and the original/remove list
        # all_remove_ids.update(ids)
        self.redundant_pairs = self.curate_by_redundant()

        logging.info(f"Total number of units to remove: {len(all_remove_ids)}")

        curated_excess = curation.remove_excess_spikes(self.we.sorting, self.we.recording)
        self.we.sorting = curated_excess
        return curated_excess.unit_ids, list(all_remove_ids)

    def prepare_rec(self, low=300., high=6000., common_ref=True):
        if self.data_format == "Maxwell":
            rec = MaxwellRecordingExtractor(file_path=self._rec_path)
            gain_uv = read_maxwell_gain(self._rec_path)
        elif self.data_format == "nwb":
            rec = se.read_nwb(self._rec_path)
            gain_uv = 1
        rec_scale = spre.ScaleRecording(rec, gain=gain_uv)
        rec_filt = spre.bandpass_filter(rec_scale, freq_min=low, freq_max=high, dtype="float32")
        if common_ref:
            rec_cmr = spre.common_reference(rec_filt)
            return rec_cmr
        else:
            return rec_filt

    def extract_waveforms(self, ms_before=2., ms_after=3., max_spikes=500):
        rec_pre = self.prepare_rec()
        self.extract_path = posixpath.join(self.base_folder, "extract_waveforms")
        if os.path.isdir(self.extract_path):
            we = sc.WaveformExtractor.load(folder=self.extract_path)
        else:
            we = sc.WaveformExtractor(rec_pre, self.phy_result, self.base_folder, allow_unfiltered=False)
            we.set_params(ms_before=ms_before, ms_after=ms_after, max_spikes_per_unit=max_spikes)
            we.run_extract_waveforms(**JOB_KWARGS)
            we.save(self.extract_path, overwrite=True)
        return we

    def compute_noise_level(self):
        rec_pre = self.prepare_rec()
        noise_levels_mv = si.get_noise_levels(rec_pre, return_scaled=True)
        return noise_levels_mv

    @property
    def curate_by_snr(self):
        num_units = len(self.we.unit_ids)
        snr = sqm.compute_snrs(self.we)
        remove_ids = []
        for k, v in snr.items():
            if v < self._snr_thres:
                remove_ids.append(k)
        cleaned_sorting = self.we.sorting.remove_units(remove_ids)
        self.we.sorting = cleaned_sorting
        logging.info(f"Curated by SNR of {self._snr_thres} rms. "
                     f"Remove number of units: {len(remove_ids)}/{num_units}")
        return remove_ids

    def curate_by_isi(self):
        """
        ISI violation by Hill method with 1.5 ms refactory period
        """
        num_units = len(self.we.unit_ids)
        isi_viol_ratio, isi_viol_num = sqm.compute_isi_violations(self.we)
        remove_ids = []
        for k, v in isi_viol_ratio.items():
            if v > self._isi_viol_thres:
                remove_ids.append(k)
        cleaned_sorting = self.we.sorting.remove_units(remove_ids)
        self.we.sorting = cleaned_sorting
        logging.info(f"Curated by ISI violation (Hill method) "
                     f"of {self._isi_viol_thres}/1 of 1.5 ms refactory period. "
                     f"Remove number of units: {len(remove_ids)}/{num_units}")
        return remove_ids
    
    def curate_by_isi_ratio(self):
        """
        ISI violation by ratio defined as number of violations over total number of spikes
        """
        # TODO
        
        pass

    def curate_by_fr(self):
        num_units = len(self.we.unit_ids)
        firing_rate = sqm.compute_firing_rates(self.we)
        remove_ids = []
        for k, v in firing_rate.items():
            if v < self._fr_thres:
                remove_ids.append(k)
        cleaned_sorting = self.we.sorting.remove_units(remove_ids)
        self.we.sorting = cleaned_sorting
        logging.info(f"Curated by firing rate of {self._fr_thres} Hz. "
                     f"Remove number of units: {len(remove_ids)}/{num_units}")
        return remove_ids

    def curate_by_redundant(self):
        num_units = len(self.we.unit_ids)
        curated_redundant, redundant_unit_pairs = \
            curation.remove_redundant_units(self.we, align=False,
                                            remove_strategy="max_spikes", extra_outputs=True)
        print("done redundant")

        remove_ids = np.setdiff1d(self.we.sorting.unit_ids, curated_redundant.unit_ids)
        logging.info(f"Curated by checking redundant units (Function turned off, no unit removed). "
                     f"Found number of units to remove: {len(remove_ids)}/{num_units}")
        # self.we.sorting = curated_redundant
        # return remove_ids
        return redundant_unit_pairs

    def package_cleaned(self):
        spike_data = self.compile_data()
        curated_file = 'qm.npz'
        curated_folder = posixpath.join(self.base_folder, "curated")
        if not os.path.isdir(curated_folder):
            os.mkdir(curated_folder)
        qm_npz = posixpath.join(curated_folder, curated_file)
        np.savez(qm_npz, **spike_data)
        shutil.move(LOG_FILE_NAME, curated_folder)
        qm_file = shutil.make_archive(posixpath.join(self.base_folder, "qm"), format="zip", root_dir=curated_folder)
        logging.info(f"Cleaned data saved to {qm_file}")
        # also package waveforms
        rec_attr = posixpath.join(self.extract_path, "recording_info", "recording_attributes.json")
        if os.path.isfile(rec_attr):
            shutil.copy(rec_attr, self.clean_folder)
        # wf_file = shutil.make_archive(posixpath.join(self.base_folder, "wf"), format="zip", root_dir=self.clean_folder)
        wf_file = None
        return qm_file, wf_file

    # def compile_data(self, n=12):
    #     """
    #     compile the cleaned sorting to npz with braingeneers compatible structure
    #     """
    #     templates = self.we_clean.get_all_templates()
    #     clusters = self.we_clean.unit_ids
    #     nc = len(clusters)
    #     channels = self.we_clean.recording.get_channel_ids()
    #     positions = self.we_clean.recording.get_channel_locations()
    #     best_channels = get_best_channel_cluster(clusters, channels, templates)
    #     neuron_dict = dict.fromkeys(np.arange(nc), None)
    #     for i in range(nc):
    #         c = clusters[i]
    #         temp = templates[i]
    #         sorted_idx = sort_template_amplitude(temp)[:n]
    #         temp = temp.T
    #         best_idx = sorted_idx[0]
    #         neuron_dict[i] = {"cluster_id": c, "channel": best_channels[c],
    #                           "position": positions[best_idx],
    #                           "template": temp[best_idx],
    #                           "neighbor_channels": channels[sorted_idx],
    #                           "neighbor_positions": positions[sorted_idx],
    #                           "neighbor_templates": temp[sorted_idx]
    #                           }
    #     if self.data_format == "Maxwell":
    #         logging.info(f"Reading electrode configuration for {self.data_format} data format")
    #         config = read_maxwell_mapping(self._rec_path)
    #     else:
    #         logging.info(f"Electrode configuration not available for {self.data_format} data format")
    #         config = {}
    #     spike_data = {"train": {c: self.we_clean.sorting.get_unit_spike_train(c)
    #                             for c in clusters},
    #                   "neuron_data": neuron_dict,
    #                   "config": config,
    #                   "redundant_pairs": self.redundant_pairs,
    #                   "fs": self.we_clean.recording.sampling_frequency}
    #     logging.info(f"Compiled data for {nc} cleaned units")
    #     return spike_data

    def compile_data(self, n=None):
        """
        compile the cleaned sorting to npz with braingeneers compatible structure
        """
        templates = self.we_clean.get_all_templates()
        clusters = self.we_clean.unit_ids
        nc = len(clusters)
        channels = self.we_clean.recording.get_channel_ids()
        positions = self.we_clean.recording.get_channel_locations()
        best_channels = get_best_channel_cluster(clusters, channels, templates)
        neuron_dict = dict.fromkeys(np.arange(nc), None)
        for i in range(nc):
            c = clusters[i]
            temp = templates[i]
            sorted_idx = sort_template_amplitude(temp)[:n] if n else sort_template_amplitude(temp)
            temp = temp.T
            best_idx = sorted_idx[0]
            neuron_dict[i] = {"cluster_id": c, "channel": best_channels[c],
                              "position": positions[best_idx],
                              "template": temp[best_idx],
                              "neighbor_channels": channels[sorted_idx],
                              "neighbor_positions": positions[sorted_idx],
                              "neighbor_templates": temp[sorted_idx]
                              }
        if self.data_format == "Maxwell":
            logging.info(f"Reading electrode configuration for {self.data_format} data format")
            config = read_maxwell_mapping(self._rec_path)
        else:
            logging.info(f"Electrode configuration not available for {self.data_format} data format")
            config = {}
        spike_data = {"train": {c: self.we_clean.sorting.get_unit_spike_train(c)
                                for c in clusters},
                      "neuron_data": neuron_dict,
                      "config": config,
                      "redundant_pairs": self.redundant_pairs,
                      "fs": self.we_clean.recording.sampling_frequency}
        logging.info(f"Compiled data for {nc} cleaned units")
        return spike_data

def read_maxwell_gain(h5_file):
    dataset = h5py.File(h5_file, 'r')
    if 'mapping' in dataset.keys():
        # Legacy MaxOne format
        gain_uv = dataset['settings']['lsb'][0] * 1e6
    else:
        # Dynamically find the correct well identifier for MaxTwo data
        rec_group = dataset['recordings']['rec0000']
        # Find well groups (well001, well002, etc.)
        well_keys = [key for key in rec_group.keys() if key.startswith('well')]
        if not well_keys:
            raise KeyError("No well groups found in the recording")
        
        # Sort well keys to ensure consistent ordering (well001, well002, etc.)
        well_keys.sort()
        well_key = well_keys[0]  # Use the first well found
        
        logging.info(f"Found wells: {well_keys}, using: {well_key}")
        gain_uv = rec_group[well_key]['settings']['lsb'][0] * 1e6
    return gain_uv


def read_maxwell_mapping(h5_file):
    with h5py.File(h5_file, 'r') as dataset:
        if 'version' and 'mxw_version' in dataset.keys():
            # Dynamically find the correct well identifier for MaxTwo data
            rec_group = dataset['recordings']['rec0000']
            # Find well groups (well001, well002, etc.)
            well_keys = [key for key in rec_group.keys() if key.startswith('well')]
            if not well_keys:
                raise KeyError("No well groups found in the recording")
            
            # Sort well keys to ensure consistent ordering (well001, well002, etc.)
            well_keys.sort()
            well_key = well_keys[0]  # Use the first well found
            
            logging.info(f"Found wells: {well_keys}, using: {well_key}")
            mapping = rec_group[well_key]['settings']['mapping']
            config = {'pos_x': np.array(mapping['x']),
                      'pos_y': np.array(mapping['y']),
                      'channel': np.array(mapping['channel']),
                      'electrode': np.array(mapping['electrode'])}
        else:
            # Legacy MaxOne format
            mapping = dataset['mapping']
            config = {'pos_x': np.array(mapping['x']),
                      'pos_y': np.array(mapping['y']),
                      'channel': np.array(mapping['channel']),
                      'electrode': np.array(mapping['electrode'])}
    return config


def get_parent_data(neuron_dict):
    parent_id_dict = {v["cluster_id"]: v for _, v in neuron_dict.items()}
    parent_ids = list(parent_id_dict.keys())
    return parent_ids, parent_id_dict


def select_units(spike_train, neuron_dict, selected_ids):
    parent_ids, parent_dict = get_parent_data(neuron_dict)
    update_dict = {}
    update_trains = []
    for i in range(len(selected_ids)):
        id = selected_ids[i]
        update_dict[i] = parent_dict[id]
        update_trains.append(spike_train[parent_ids.index(id)])
    return update_trains, update_dict

def remove_units(spike_train, neuron_dict, removed_ids):
    parent_ids, _ = get_parent_data(neuron_dict)
    selected_ids = np.setdiff1d(parent_ids, removed_ids)
    update_trains, update_dict = select_units(spike_train, neuron_dict, selected_ids)
    return update_trains, update_dict

# def upload_file(phy_path, local_file, params_file_name=None):
#     # create upload path by appending parameter file to the phy path and hash string
#     if params_file_name is None:
#         upload_path = phy_path.replace("_phy.zip", "_acqm.zip")
#     else:
#         upload_path = phy_path.replace("_phy.zip", f"_{params_file_name}_acqm.zip")
#     upload_path = upload_path.replace("kilosort2", "autocuration")
#     logging.info(f"Uploading data from {local_file} to {upload_path} ...")
#     wr.upload(local_file=local_file, path=upload_path)
#     logging.info("Done!")

def upload_file(phy_path, local_file, local=True, params_file_name=None, local_base_dir=None):

    # create upload/save path
    if params_file_name is None:
        target_path = phy_path.replace("_phy.zip", "_acqm.zip")
    else:
        target_path = phy_path.replace("_phy.zip", f"_{params_file_name}_acqm.zip")
    target_path = target_path.replace("kilosort2", "autocuration")

    if local:
        # Fix path
        if local_base_dir is None:
            local_base_dir = os.getcwd()
        local_path = target_path.replace("s3://", "")
        save_path = os.path.join(local_base_dir, local_path)
        
        # Create directories if needed
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        logging.info(f"Saving data from {local_file} to {save_path} ...")
        shutil.copy(local_file, save_path)
        logging.info("Done!")
        return save_path
    else:
        # Upload to S3
        logging.info(f"Uploading data from {local_file} to {target_path} ...")
        wr.upload(local_file=local_file, path=target_path)
        logging.info("Done!")
        return target_path

def parse_uuid(data_path):
    experiment = data_path.split("/")[-1]
    base_path = data_path.split(experiment)[0]
    if "original/data" in base_path:
        phy_base_path = base_path.replace("original/data", "derived/kilosort2")
        metadata_path = base_path.split("original/data")[0] + "metadata.json"
    elif "shared" in base_path:
        phy_base_path = base_path.replace("shared", "derived/kilosort2")
        metadata_path = base_path.split("shared")[0] + "metadata.json"
        
    if experiment.endswith(".raw.h5"):
        experiment = experiment.split(".raw.h5")[0]
    elif experiment.endswith(".h5"):
        pass
    else:
        experiment = experiment.split(".")[0]
    phy_path = posixpath.join(phy_base_path, experiment + "_phy.zip")
    return base_path, experiment, metadata_path, phy_path

def hash_file_name(input_string):
    import hashlib
    md5_hash = hashlib.md5()
    md5_hash.update(input_string.encode('utf-8'))
    hash_string = md5_hash.hexdigest()
    return hash_string


# Copied from utils.py >>>>>> 

def read_phy_files(path: str, fs=20000.0):
    """
    :param path: a s3 or local path to a zip of phy files.
    :return: SpikeData class with a list of spike time lists and neuron_data.
            neuron_data = {0: neuron_dict, 1: config_dict}
            neuron_dict = {"new_cluster_id": {"channel": c, "position": (x, y),
                            "amplitudes": [a0, a1, an], "template": [t0, t1, tn],
                            "neighbor_channels": [c0, c1, cn],
                            "neighbor_positions": [(x0, y0), (x1, y1), (xn,yn)],
                            "neighbor_templates": [[t00, t01, t0n], [tn0, tn1, tnn]}}
            config_dict = {chn: pos}
    """
    assert path[-3:] == 'zip', 'Only zip files supported!'
    import braingeneers.utils.smart_open_braingeneers as smart_open
    with smart_open.open(path, 'rb') as f0:
        f = io.BytesIO(f0.read())

        with zipfile.ZipFile(f, 'r') as f_zip:
            assert 'params.py' in f_zip.namelist(), "Wrong spike sorting output."
            with io.TextIOWrapper(f_zip.open('params.py'), encoding='utf-8') as params:
                for line in params:
                    if "sample_rate" in line:
                        fs = float(line.split()[-1])
            clusters = np.load(f_zip.open('spike_clusters.npy')).squeeze()
            templates_w = np.load(f_zip.open('templates.npy'))  # (cluster_id, samples, channel_id)
            wmi = np.load(f_zip.open('whitening_mat_inv.npy'))
            channels = np.load(f_zip.open('channel_map.npy')).squeeze()
            spike_templates = np.load(f_zip.open('spike_templates.npy')).squeeze()
            spike_times = np.load(f_zip.open('spike_times.npy')).squeeze() / fs * 1e3  # in ms
            positions = np.load(f_zip.open('channel_positions.npy'))
            amplitudes = np.load(f_zip.open("amplitudes.npy")).squeeze()
            if 'cluster_info.tsv' in f_zip.namelist():
                cluster_info = pd.read_csv(f_zip.open('cluster_info.tsv'), sep='\t')
                cluster_id = np.array(cluster_info['cluster_id'])
                # select clusters using curation label, remove units labeled as "noise"
                # find the best channel by amplitude
                labeled_clusters = cluster_id[cluster_info['group'] != "noise"]
            else:
                labeled_clusters = np.unique(clusters)

    # unwhite the templates before finding the best channel!
    templates = np.dot(templates_w, wmi)

    df = pd.DataFrame({"clusters": clusters, "spikeTimes": spike_times, "amplitudes": amplitudes})
    cluster_agg = df.groupby("clusters").agg({"spikeTimes": lambda x: list(x),
                                              "amplitudes": lambda x: list(x)})
    cluster_agg = cluster_agg[cluster_agg.index.isin(labeled_clusters)]
    cls_temp = dict(zip(clusters, spike_templates))
    neuron_dict = dict.fromkeys(np.arange(len(labeled_clusters)), None)

    for i in range(len(labeled_clusters)):
        c = labeled_clusters[i]
        temp = templates[cls_temp[c]]
        amp = np.max(temp, axis=0) - np.min(temp, axis=0)
        sorted_idx = np.argsort(amp)[::-1]
        nbgh_chan_idx = sorted_idx[:12]
        nbgh_temps = temp.transpose()[sorted_idx]
        best_chan_temp = nbgh_temps[0]
        nbgh_channels = channels[nbgh_chan_idx]
        nbgh_postions = [tuple(positions[idx]) for idx in nbgh_chan_idx]
        best_channel = nbgh_channels[0]
        best_position = nbgh_postions[0]
        cls_amp = cluster_agg["amplitudes"][c]
        neuron_dict[i] = {"cluster_id": c, "channel": best_channel, "position": best_position,
                          "amplitudes": cls_amp, "template": best_chan_temp,
                          "neighbor_channels": nbgh_channels, "neighbor_positions": nbgh_postions,
                          "neighbor_templates": nbgh_temps}
    config_dict = dict(zip(channels, positions))
    neuron_data = {0: neuron_dict}
    metadata = {0: config_dict}
    spike_train = list(cluster_agg["spikeTimes"])
    return fs, spike_train, neuron_dict


def sort_template_amplitude(template):
    """
    sort template by amplitude from the largest to the smallest
    :param template: N x M array template array as N for the length of samples,
                     and M for the length of channels
    :return: sorted template index
    """
    assert template.ndim == 2, "Input should be a 2D array; use sort_templates() for higher dimensional data"
    amp = np.max(template, axis=0) - np.min(template, axis=0)
    sorted_idx = np.argsort(amp)[::-1]
    return sorted_idx

def get_best_channel(channels, template):
    assert len(channels) == template.shape[1], "The number of channels does not match to template"
    idx = sort_template_amplitude(template)
    return channels[idx[0]]

def get_best_channel_cluster(clusters, channels, templates):
    """
    find the best channel by sorting templates by amplitude.
    :param clusters:
    :param channels:
    :param templates:
    :return:
    """
    assert len(clusters) == len(templates), "The number of clusters not equal to the number of templates"
    best_channel = dict.fromkeys(clusters)
    for i in range(len(clusters)):
        cls = clusters[i]
        temp = templates[i]
        best_channel[cls] = get_best_channel(channels, temp)
    return best_channel


def get_best_channel_position(channel_position, template):
    idx = sort_template_amplitude(template)
    return channel_position[idx]


def sort_channel_distance(channel_positions, best_channel_position):
    """
    sort channel location by distance to the best channel
    """
    x0, y0 = best_channel_position[0], best_channel_position[1]
    distance = np.empty(len(channel_positions))
    for i in range(len(channel_positions)):
        pos = channel_positions[i]
        distance[i] = (pos[0]-x0)**2 + (pos[1]-y0)**2
    return np.argsort(distance)

    # <<<<<<<< 


if __name__ == "__main__":

    '''
    How to use: 
        - python3 si_curation2.py <phy.zip location> <raw.h5 location>
        - 
    '''
    
    # data_path = sys.argv[1]
    # param_path = sys.argv[2]
    # param_path=None
    # params_file_name = param_path.split("/")[-1].split(".")[0]

    data_path = sys.argv[1]
    phy_path = sys.argv[2]
    data_path= '/Users/noah/Desktop/sharf_lab/sharflab_code/noacode/learning/sampleFiles/24432_10Feb2026/24432_10Feb2026.raw.h5'
    phy_path = '/Users/noah/Desktop/sharf_lab/sharflab_code/noacode/learning/sampleFiles/24432_10Feb2026/24432_10Feb2026_phy'

    setup_hdf5()
 
    # s3_base_path, experiment, metadata_path, phy_path = parse_uuid(data_path=data_path)
    print(f"data path: {data_path}")  # original recording s3 full path
    # print(f"base path: {s3_base_path}")
    # print(f"metadata path: {metadata_path}")
    print(f"phy path: {phy_path}")
    # print(f"parameter file path: {param_path}")

    # download file from s3
    # current_folder = os.getcwd()
    current_folder = "/tmp"   # to make sure the volumn mount works
    subfolder = "/data"
    base_folder = current_folder + subfolder

    if not os.path.isdir(base_folder):
        os.mkdir(base_folder)
    print(base_folder)
    extract_dir = base_folder + "/kilosort_result"
    kilosort_local_path = posixpath.join(base_folder, "kilosort_result.zip")
    metadata_local_path = posixpath.join(base_folder, "metadata.json")

    # for p in [phy_path, data_path, param_path]:
    # COMMENTED OUT FOR LOCAL OPERATION - NO S3
    # for p in [phy_path, data_path]:
    #     try:
    #         assert wr.does_object_exist(p)
    #     except AssertionError as err:
    #         logging.exception(f"File doesn't exist on S3! {p}")
    #         logging.info("Program exited")
    #         raise err

    # Check if local files exist instead
    for p in [phy_path, data_path]:
        if not os.path.exists(p):
            logging.error(f"File doesn't exist locally! {p}")
            logging.info("Program exited")
            raise FileNotFoundError(f"File not found: {p}")
    
    # >>>>>>>>>>
    # # download metadata
    # if wr.does_object_exist(metadata_path):
    #     logging.info("Start downloading metadata ...")
    #     wr.download(metadata_path, metadata_local_path)
    #     logging.info("Done!")
    #     with open(metadata_local_path, "r") as f:
    #         metadata = json.load(f)
    #         if (experiment in metadata["ephys_experiments"]) and \
    #                 ("data_format" in metadata["ephys_experiments"][experiment]):
    #             data_format = metadata["ephys_experiments"][experiment]["data_format"]
    #             logging.info(f"Read data format from metadata.json, format is {data_format}")
    #         else:
    #             data_format = "Maxwell"  # a patch for the old metadata.json
    #             logging.info(f"Data format not found in metadata.json, default to Maxwell")
    # else:
    #     logging.info("Metadata file not found. Skip downloading metadata.")
    #     logging.info("Data format default to Maxwell")
    #     data_format = "Maxwell"
    # <<<<<<<<<<<<<

    logging.info("Metadata file not found. Skip downloading metadata.")
    logging.info("Data format default to Maxwell")
    data_format = "Maxwell"

    # Extract experiment name from data_path for local operation
    experiment_filename = os.path.basename(data_path)
    if experiment_filename.endswith(".raw.h5"):
        experiment = experiment_filename.replace(".raw.h5", "")
    elif experiment_filename.endswith(".h5"):
        experiment = experiment_filename.replace(".h5", "")
    else:
        experiment = os.path.splitext(experiment_filename)[0]
    logging.info(f"Experiment name: {experiment}")

    # # download phy.zip
    # COMMENTED OUT FOR LOCAL OPERATION
    # logging.info("Start downloading kilosort result ...")
    # wr.download(phy_path, kilosort_local_path)
    # logging.info("Done!")
    # shutil.unpack_archive(kilosort_local_path, extract_dir, "zip")

    # Copy local kilosort results instead of downloading
    logging.info("Copying local kilosort results...")
    if os.path.isdir(phy_path):
        # phy_path is a directory, copy it directly
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        shutil.copytree(phy_path, extract_dir)
    else:
        # phy_path is a zip file, unpack it
        shutil.unpack_archive(phy_path, extract_dir, "zip")
    logging.info("Done!")

    # # download raw data
    # COMMENTED OUT FOR LOCAL OPERATION
    # logging.info("Start downloading raw data ...")
    # experiment = "rec"
    # wr.download(data_path, posixpath.join(base_folder, experiment))
    # logging.info("Done")

    # Copy local raw data instead of downloading
    logging.info("Copying local raw data...")
    local_data_path = posixpath.join(base_folder, experiment + ".raw.h5")
    shutil.copy(data_path, local_data_path)
    logging.info("Done!")

    # >>>>>>>>>>>>
    ### Bypassed in favor of always using default
    # download param file
    # logging.info("Start downloading parameter file ...")
    # param_file = posixpath.join(base_folder, "params.json")
    # wr.download(param_path, param_file)
    # logging.info("Done")
    # with open(param_file, "r") as f:
    #     params_dict = json.load(f)
    # if len(params_dict) > 0:
    #     logging.info(f"Use parameters {params_dict} from file {param_path} for curation")
    # else:
    #     params_file_name = "params_updated_default"
    #     logging.info(f"User parameters not available. Use updated default parameters {DEFUALT_PARAMS} for curation")

    logging.info(f"Using updated default parameters {DEFUALT_PARAMS} for curation")
    params_dict = DEFUALT_PARAMS

    # <<<<<<<<<<<

    # Clean up old temporary files from previous runs
    cleanup_folders = [
        posixpath.join(base_folder, "extract_waveforms"),
        posixpath.join(base_folder, "cleaned_waveforms"),
        posixpath.join(base_folder, "curated")
    ]
    for folder in cleanup_folders:
        if os.path.exists(folder):
            logging.info(f"Removing old temporary folder: {folder}")
            shutil.rmtree(folder)


    # do curation
    # rec_name should match the copied file name
    rec_name = experiment + ".raw.h5"
    curation = QualityMetrics(base_folder=base_folder,
                              rec_name=rec_name,
                              phy_folder=extract_dir,
                              data_format=data_format,
                              params_dict=params_dict)
    qm_file, wf_file = curation.package_cleaned()

    # curated_file = experiment + "_qm.zip"
    # waveform_file = experiment + "_wf.zip"
    # MODIFIED FOR LOCAL OPERATION - save locally instead of uploading to S3
    # Save the acqm.zip in the same directory as the original data
    data_dir = os.path.dirname(data_path)
    acqm_filename = experiment + "_acqm.zip"
    acqm_path = os.path.join(data_dir, acqm_filename)
    logging.info(f"Saving curated data to {acqm_path} ...")
    shutil.copy(qm_file, acqm_path)
    logging.info("Done!")
    # upload_file(phy_path, qm_file, local=True, params_file_name=None, local_base_dir=os.getcwd())
    # upload_file(uuid, wf_file, waveform_file)

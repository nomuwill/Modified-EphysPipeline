import numpy as np
import spikeinterface.extractors as se
import os

# Get base directory from environment variable, default to /project/SpikeSorting
SPIKE_SORTING_BASE = os.environ.get("SPIKE_SORTING_DIR", "/project/SpikeSorting")

# List of data files you want to spike sort
rec_file = f"{SPIKE_SORTING_BASE}/Trace"

# List of intermediate folders where tmp and output files are saved
inter_folder = f"{SPIKE_SORTING_BASE}/inter"

# # List of output folders where final matlab files are saved.
# # Matlab files will have the same name as recording files but will end with _sorted.mat
# matlab_folder = "/project/SpikeSorting/output"

# Get script directory for relative paths
_script_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_script_dir)  # Parent of src/ is the repo root

# standalone executable absolute path (relative to repo)
stdln_folder = os.environ.get("KILOSORT_MATLAB_DIR", os.path.join(_repo_root, "matlab"))
stdln_script = "run_kilosort_compiled.sh"
# MATLAB runtime directory as required for running the standalone shell script
runtime_folder = os.environ.get("MATLAB_RUNTIME_DIR", "/usr/local/MATLAB/MATLAB_Runtime/v97")

# Set toolbox paths
kilosort_path = stdln_folder
hdf5_plugin_path = os.environ.get("HDF5_PLUGIN_PATH", _script_dir)

# preprocess parameters
band_min, band_max = 300, 6000

# Sorter params
kilosort_params = {
    'detect_threshold': 6,
    'projection_threshold': [10, 4],
    'preclust_threshold': 8,
    'car': 1,
    'minFR': 0.1,
    'minfr_goodchannels': 0.1,
    'freq_min': 150,
    'sigmaMask': 30,
    'nPCs': 3,
    'ntbuff': 64,
    'nfilt_factor': 4,
    'NT': 65600,
    'keep_good_only': False,
    'total_memory': "2G",
    'n_jobs_bin': 64,
    'trange': [float(0), float('inf')]
}
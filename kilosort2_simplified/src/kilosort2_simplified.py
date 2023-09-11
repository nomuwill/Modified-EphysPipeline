import spikeinterface.extractors as se
import spikeinterface.preprocessing as sp
import os
import MEArec as mr
from kilosort2_params import *
from scipy.io import savemat
import subprocess


def run_sorting(rec_path, output_folder, format):
    rec = extract_recording(rec_path=rec_path, output_folder=output_folder, format=format)
    assert rec != -1, "Cannot read this recording"

    rec_filter = sp.bandpass_filter(rec, freq_min=band_min, freq_max=band_max)
    sorting = run_kilosort(rec_filter, output_folder)
    assert sorting == 0, " Kilosort returned non-zero value"
    # package files into a zip


def run_kilosort(rec, output_folder):
    create_config(recording=rec, output_folder=output_folder)
    print("Start running Kilosort...")
    kilosort_shell = os.path.join(stdln_folder, stdln_script)
    os.chdir(stdln_folder)
    psort = subprocess.Popen(["bash", kilosort_shell, runtime_folder, output_folder])
    # wait until subprocess finish
    ret = psort.wait()
    return ret


def extract_recording(rec_path: str, output_folder: str, format: str):
    rec = None
    assert format in ["maxwell", "mearec"], "Data format not supported"
    if format == "mearec":
        mr.convert_recording_to_new_version(rec_path)
        rec, _ = se.read_mearec(rec_path)
    elif format == "maxwell":
        rec = se.read_maxwell(rec_path)
    # convert to binary recording
    binary_file_path = os.path.join(output_folder, 'recording.dat')
    se.BinaryRecordingExtractor.write_recording(
        rec, file_paths=binary_file_path,
        dtype='int16', total_memory=kilosort_params["total_memory"],
        n_jobs=kilosort_params["n_jobs_bin"],
        verbose=False, progress_bar=True)
    return rec


def create_config(recording, output_folder):
    """
    create ops.mat and chanMap.mat
    """
    groups = [1] * recording.get_num_channels()
    positions = np.array(recording.get_channel_locations())

    # TODO: keep errors in logging
    assert positions.shape[1] == 2, "Set 2D channel locations"
    # create ops.mat
    ops = {}
    ops_dict = {}
    ops_dict["NchanTOT"] = float(recording.get_num_channels())
    ops_dict["Nchan"] = float(recording.get_num_channels())
    ops_dict["fs"] = float(recording.get_sampling_frequency())
    ops_dict["datatype"] = 'dat'
    ops_dict["fbinary"] = os.path.join(output_folder, 'recording.dat')
    ops_dict["fproc"] = os.path.join(output_folder, 'temp_wh.dat')
    ops_dict["root"] = str(output_folder)
    ops_dict["chanMap"] = os.path.join(output_folder, 'chanMap.mat')
    ops_dict["fshigh"] = float(kilosort_params['freq_min'])
    ops_dict["minfr_goodchannels"] = float(kilosort_params['minfr_goodchannels'])
    ops_dict["Th"] = list(map(float, kilosort_params['projection_threshold']))
    ops_dict["lam"] = float(10)
    ops_dict["AUCsplit"] = 0.9
    ops_dict["minFR"] = float(kilosort_params['minFR'])
    ops_dict["momentum"] = list(map(float, np.array([20, 400])))
    ops_dict["sigmaMask"] = float(kilosort_params['sigmaMask'])
    ops_dict["ThPre"] = float(kilosort_params['preclust_threshold'])
    ops_dict["spkTh"] = float(-kilosort_params['detect_threshold'])
    ops_dict["reorder"] = float(1)
    ops_dict["nskip"] = float(25)
    ops_dict["CAR"] = float(kilosort_params['car'])
    ops_dict["GPU"] = float(1)
    ops_dict["nfilt_factor"] = float(kilosort_params['nfilt_factor'])
    ops_dict["ntbuff"] = float(kilosort_params['ntbuff'])
    ops_dict["NT"] = float(kilosort_params['NT'])
    ops_dict["whiteningRange"] = float(32)
    ops_dict["nSkipCov"] = float(25)
    ops_dict["scaleproc"] = float(200)
    ops_dict["nPCs"] = float(kilosort_params['nPCs'])
    ops_dict["useRAM"] = float(0)
    ops_dict["trange"] = kilosort_params['trange']  # trange is float, line 56
    ops["ops"] = ops_dict
    # create mat data files
    savemat(os.path.join(output_folder, 'ops.mat'), ops)

    # create chanMap.mat
    chan_dict = {}
    chan_dict["Nchannels"] = float(recording.get_num_channels())
    chan_dict["connected"] = [True] * int(recording.get_num_channels())
    chan_dict["chanMap"] = list(
        map(float, np.array(range(int(recording.get_num_channels()))) + 1))  # MATLAB counts from 1
    chan_dict["chanMap0ind"] = list(map(float, np.array(range(int(recording.get_num_channels())))))
    chan_dict["xcoords"] = [p[0] for p in positions]
    chan_dict["ycoords"] = [p[1] for p in positions]
    chan_dict["kcoords"] = list(map(float, groups))
    chan_dict["fs"] = float(recording.get_sampling_frequency())
    savemat(os.path.join(output_folder, 'chanMap.mat'), chan_dict, oned_as='column')


if __name__ == "__main__":
    output_folder = os.path.join(inter_folder, "sorted/kilosort2")
    run_sorting(rec_path=rec_file, output_folder=output_folder, format="mearec")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import seaborn as sns
from fr_extractor import *
import pandas as pd


fs = 20000.0
plt.style.use('default')


def plot_fr_days(c_mean, c_error, p_mean, p_error, group, days):
    fig, axs = plt.subplots(1, 1, figsize=(5, 5), constrained_layout=True)
    axs.set_title("Fr of {}".format(group), fontsize=16)
    offset = 0  # 0.15
    (_, caps, _) =  axs.errorbar(np.arange(len(days))-offset, c_mean, yerr=c_error, 
                                marker='o', linewidth=2, markersize=8, capsize=4, color='b',
                                label="Control")
    for cap in caps:
        cap.set_markeredgewidth(1)
    (_, caps, _) =  axs.errorbar(np.arange(len(days))+offset, p_mean, yerr=p_error, 
                                marker='D', linewidth=2, markersize=8, capsize=4, color='r', 
                                label="Patient")
    for cap in caps:
        cap.set_markeredgewidth(1)
    axs.legend(loc="upper right", fontsize=12)
    axs.set_xlabel('days', fontsize=16)
    axs.set_ylabel('Fr (Hz)', fontsize=16)
    axs.set_xticks(np.arange(len(days)))
    axs.set_xticklabels(days)
    axs.xaxis.set_tick_params(labelsize=16)
    axs.yaxis.set_tick_params(labelsize=16)
    # axs.set_ylim([0, max(max(c_mean), max(p_mean))+1.5])
    axs.set_ylim(0, 5.5)
    plt.savefig("Fr_for_{}.png".format(group), dpi=300)


def plot_num_units(cp_data, days, group):
    fig, axs = plt.subplots(1, 1, figsize=(5, 5), constrained_layout=True)
    axs.set_title("Num Units, {}".format(group), fontsize=16)
    xx = np.arange(len(days))
    yy_c = [len(times) for times in cp_data["control"]]
    yy_p = [len(times) for times in cp_data["patient"]]
    axs.plot(xx, yy_c, color='b', alpha=0.8, marker="o", linewidth=2, markersize=8, label="Control")
    for i, txt in enumerate(yy_c):
        axs.annotate(txt, (xx[i], yy_c[i]), fontsize=12)
    axs.plot(xx, yy_p, color='r', alpha=0.8, marker="D", linewidth=2, markersize=8, label="Patient")
    for i, txt in enumerate(yy_p):
        axs.annotate(txt, (xx[i], yy_p[i]), fontsize=12)
    axs.legend(loc="upper right", fontsize=12)
    axs.set_xlabel('days', fontsize=16)
    axs.set_ylabel('Counts', fontsize=16)
    axs.set_xticks(np.arange(len(days)))
    axs.set_xticklabels(days)
    axs.xaxis.set_tick_params(labelsize=16)
    axs.yaxis.set_tick_params(labelsize=16)
    plt.savefig("Num_Units_{}.png".format(group, dpi=300)) 

def plot_violin(cp_data, days, file_name):
    import seaborn as sns
    import pandas as pd
    data = dict(zip(days, cp_data['control']))
    control = pd.DataFrame.from_dict(data, orient='index').transpose()
    patient = pd.DataFrame.from_dict(dict(zip(days, cp_data['patient'])), orient='index').transpose()
    df = pd.DataFrame([[label, val, 'control'] for label, values in control.items() for val in values]
                    + [[label, val, 'patient'] for label, values in patient.items() for val in values],
                    columns=['label', 'value', 'source'])

    fig, ax = plt.subplots(2, 1, figsize = (7, 4*2), constrained_layout=True)
    ax[0].set_title("Fr {}".format(file_name), fontsize=16)
    axs = ax[0]
    axs1 = ax[1]
    axs = sns.violinplot(data=df, x='label', y='value', hue='source', inner="box",
                        palette=['cornflowerblue', 'indianred'], ax=axs)
    sns.stripplot(data=df, x='label', y='value', hue='source', dodge=True, jitter=True, linewidth=0.4, size=3, 
                palette=['cornflowerblue', 'indianred'], ax=axs)

    sns.violinplot(data=df, x='label', y='value', hue='source', palette=['cornflowerblue', 'indianred'], saturation=0.5,
                inner="quartile", split=True, ax=axs1)
    sns.pointplot(data=df, x='label', y='value', hue='source', linestyles="", dodge=True, 
                estimator='mean', markers=["o", "D"], palette=['blue', 'red'], ax=axs1)
    for l in axs1.lines[1::3]:
        l.set_linestyle('-')
        l.set_linewidth(2)
        l.set_color('black')
        l.set_alpha(0.8)

    for a in ax:    
        a.set_ylabel("Firing Rate (Hz)", fontsize=16)
        a.set_xlabel("", fontsize=16)
        a.xaxis.set_tick_params(labelsize=16)
        a.yaxis.set_tick_params(labelsize=16)
        a.legend(loc="upper right", fontsize=12)
        a.set_ylim(-4, 30)

    plt.savefig("violin_fr_{}.png".format(file_name), dpi=300)

def fano_factor(trains: list, bin_size=0.1):
    rec_length = np.max(np.hstack(trains))
    bins = np.arange(0, rec_length+bin_size, bin_size)
    factors = []
    for t in trains:
        fr = np.histogram(t, bins)
        fano = np.var(fr) / np.mean(fr)
        factors.append(fano)
    return factors

def get_population_fr(trains: list, bin_size=0.1, w=5, average=False):
    N = len(trains)
    trains = np.hstack(trains)
    rec_length = np.max(trains)
    bin_num = int(rec_length// bin_size) + 1
    bins = np.linspace(0, rec_length, bin_num)
    fr = np.histogram(trains, bins)[0]
    fr_avg = np.convolve(fr, np.ones(w), 'same') / w
    if average:
        fr_avg /= N
    return bins, fr_avg

def plot_raster_with_fr(train:list, words:list, avg=False, axs=None):
    bins, fr_avg = get_population_fr(trains=train, average=avg)
    if axs is None:
        fig, axs = plt.subplots(1, 1, figsize=(16, 6))
    axs.set_title(f"raster_{words}", fontsize=12)

    y = 0
    for vv in train:
        axs.scatter(vv, [y]*len(vv), marker="|", c='k', s=4, alpha=0.7)
        y += 1
    axs.set_xlabel("Time (s)", fontsize=16)
    axs.set_ylabel("Unit", fontsize=16)
    axs.xaxis.set_tick_params(labelsize=16)
    axs.yaxis.set_tick_params(labelsize=16)
    
    axs1 = axs.twinx()
    axs1.yaxis.set_label_position("right") 
    axs1.spines['right'].set_color('r')
    axs1.spines['right'].set_linewidth(3)
    axs1.plot(bins[1:], fr_avg, color='r', linewidth=3, alpha=0.5)
    axs1.set_ylabel("Population Firing Rate (Hz)", fontsize=16, color='r')
    axs1.set_xlabel("Time (s)", fontsize=16)
    axs1.yaxis.set_tick_params(labelsize=16)
    axs1.spines['top'].set_visible(False)
    axs1.get_xaxis().set_visible(False)
    axs1.tick_params(left=False, right=True, labelleft=False, labelright=True,
                    bottom=False, labelbottom=True)
    axs1.tick_params(axis='y', colors='r')
    
    # plt.savefig(f"raster_{words}.png", dpi=300)

    return axs

def plot_raster_for_chip(train_dict: dict, words: list):
    for chip, days in train_dict.items():
        rows = len(days)
        all_days = list(days.keys())
        fig, axs = plt.subplots(rows, 1, figsize=(16, 6*rows), tight_layout=True)
        plt.suptitle(f"raster_of_chip{chip}_{words}", fontsize=12)
        for d, train in days.items():
            i = all_days.index(d)
            plot_raster_with_fr(train=train, words=[], axs=axs[i], use_axs=True)
        plt.savefig(f"raster_of_chip{chip}_{words}.png", dpi=300)


def plot_distribution(data_dict, func=get_group_data, type="violin", p_test=True, title="distribution", 
                      ylim=[0, 9], ylabel="LABEL", save=False, verbose=False):
    for clt, culture in data_dict.items():
        all_grp = list(culture.keys())
        for n in range(0, len(all_grp), 2):    
            if all_grp[n][0] != "C":
                grp = all_grp[n+1], all_grp[n]
            else:
                grp = all_grp[n], all_grp[n+1]
            
            if verbose:
                print(f"Culture {clt}, Group {grp}")

            fig, axs = plt.subplots(1, 1, figsize=(7, 5), constrained_layout=True)
            axs.set_title(f"{title} of {clt}, {grp}", fontsize=16)

            cv_pairs = func(data_dict, clt, grp)

            control, patient = cv_pairs
            control_mean = [np.mean(value) for d, value in control.items()]
            patient_mean = [np.mean(value) for d, value in patient.items()]
            df = pd.DataFrame([[label, val, grp[0]] for label, values in control.items() for val in values]
                        + [[label, val, grp[1]] for label, values in patient.items() for val in values],
                        columns=['days', 'value', 'source'])

            if type == "violin":
                axs = sns.violinplot(data=df, x='days', y='value', hue='source', inner="box",
                            palette=['cornflowerblue', 'indianred'], ax=axs)
            else:
                axs = sns.boxplot(data=df, x='days', y='value', hue='source', showfliers=False,
                            palette=['cornflowerblue', 'indianred'], ax=axs)
            # draw the mean
            axs.plot(np.arange(len(control_mean)), control_mean, "-x", color='b', linewidth=3, alpha=0.7)
            axs.plot(np.arange(len(patient_mean)), patient_mean, "-o", color='r', linewidth=3, alpha=0.7)

            # ks test for each day, print p value
            if p_test:
                p_values = p_test_ks(control, patient)
                axs1 = axs.twinx()
                for i, k in enumerate(p_values):
                    p = p_values[k] 
                    if p <= 0.001:
                        axs1.text(i, 0.8, "***", fontsize=16)
                    elif 0.001 < p <= 0.01:
                        axs1.text(i, 0.8, "**", fontsize=16)
                    elif 0.01 < p <= 0.05:
                        axs1.text(i, 0.8, "*", fontsize=16)
                    else:
                        axs1.text(i, 0.8, "NS", fontsize=16)
                axs1.get_yaxis().set_visible(False)
                    
            axs.set_ylim(ylim)
            axs.set_ylabel(ylabel, fontsize=16)
            axs.set_xlabel("", fontsize=16)
            axs.xaxis.set_tick_params(labelsize=16)
            axs.yaxis.set_tick_params(labelsize=16)
            axs.legend(loc="upper right", fontsize=12)
            if save:
                plt.savefig(f"{title}_{clt}_{grp}.png", dpi=300)
            plt.show(block=False)

# def plot_activity_map():
    
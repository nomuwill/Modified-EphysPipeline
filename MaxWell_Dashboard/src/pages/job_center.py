import dash
from dash import html, dcc, callback, Input, Output, State, ctx
from dash import dash_table
import braingeneers.utils.s3wrangler as wr
import dash_bootstrap_components as dbc
import os
from datetime import datetime
import braingeneers.data.datasets_electrophysiology as de
import braingeneers.utils.smart_open_braingeneers as smart_open
import json
import sys
import time

# TODO: Deal with inconsistent index when user remove rows?

dash.register_page(__name__)
sys.path.append('..')
import utils
from values import *

####----------------------- make page -----------------------####
# table layout
table_layout = dash_table.DataTable(
    id="job_table",
    columns=[
        {'id': h, 'name': h} for h in TABLE_HEADERS],
    data=[],
    # editable=True,  # This allows user to change value in each cell. So I disabled it.
    row_deletable=True
)

# page layout
print(f"Getting ready for page layout... ")
layout = dbc.Container([
    html.H2("Data Processing Center"),
    # html.Br(),
    html.Hr(),
    dbc.Row(html.Div([
        html.Div(["Dataset (UUID) ",
                  dcc.Dropdown(
                      options=[],
                      value="",
                      id="dropdown",
                      disabled=False),
                  ]),
        html.Div(["Filter UUID by Keyword: ",
                  dcc.Textarea(
                      id='textarea_filter_uuid',
                      placeholder="enter you keyword here",
                      value='',
                      style={'width': '30%', 'height': 30}, )
                  ]),
    ]),
    ),
    html.Br(),
    dbc.Row(html.Div([
        html.Div([dcc.Textarea(
            id='textarea_metadata',
            value='',
            contentEditable=False,
            readOnly=True,
            style={'width': '50%', 'height': 150}, )
        ]),
    ])
    ),
    html.Hr(),
    dbc.Row([dbc.Col([dcc.RadioItems(id="batch_job",
                                     options=[{"label": "Batch Process with Standard Pipeline",
                                               "value": "Batch"},
                                              {"label": "Clear All Selected", "value": "Reset"}],
                                     value="",)
                      ]),
             ]),
    html.Br(),
    dbc.Row([dbc.Col(dbc.Card(["Recording: ",
                               dcc.RadioItems(
                                   id='select_recording',
                                   options=[{'label': 'Select All', 'value': 'Batch'},
                                            {'label': 'Reset', 'value': 'Reset'}],
                                   value="",
                                   labelStyle={'display': 'inline'},
                               ),
                               html.P(""),
                               dcc.Checklist(
                                   id="checklist_recs",
                                   options=[],
                                   value=[],
                               )
                               ], style={"width": "18rem"}), width="auto"),
             html.Br(),
             dbc.Col(dbc.Card(["Select job: ",
                               dcc.Checklist(
                                   id='select_jobs',
                                   options=[{'label': 'Ephys Pipeline (Kilosort2, Auto-Curation, Visualization)',
                                             'value': 0},
                                            {'label': 'Spike Sorting (Kilosort2)', 'value': 1},
                                            {'label': 'Auto-Curation (Quality Metrics)', 'value': 2},
                                            {'label': 'Visualization', 'value': 3},
                                            {'label': 'Functional Connectivity', 'value': 4},
                                            {'label': 'Local Field Potential Subbands', 'value': 5}],
                                   value=[],
                                   labelStyle={'display': 'block'},
                               ),
                               html.Br(style={"line-height": "1"}),
                               ],), width="auto"),
                ]),
    html.Br(),
    # New row for parameter setting
    dbc.Row([dbc.Col(dbc.Card(["Set new parameters: ",
                               dbc.CardBody(id="set_parameter"),
                               dbc.Button("Save Parameters",
                                          id='save_param_button',
                                          disabled=False,
                                          outline=True,
                                          color="success",
                                          className="me-1"),
                               html.Div(id="save_param_return"),
                               ]), width="auto"),
             html.Br(),
             dbc.Col(dbc.Card(["Select a job to load parameter file: ",
                               dbc.CardBody(id="load_job_param"),
                               dcc.Textarea(
                                    id="display_param",
                                    value="",
                                    contentEditable=False,
                                    readOnly=True,
                                    style={'width': '70%', 'height': 150}, 
                                ),
                                html.Br(),
                                dbc.Button("Reload",
                                           id="reload_param_button",
                                           disabled=False,
                                           outline=True,
                                           color="success",
                                           className="me-1"),
                                dbc.Button("Add to Parameter Table",
                                           id="add_param_button",
                                           disabled=False,
                                           outline=True,
                                           color="success",
                                           className="me-1"),
                                html.Div(id="add_param_return"),
                                ]), width="auto"),
             html.Br(),
             dbc.Col(dbc.Card(["Current parameter setting: ", 
                            dash_table.DataTable(
                                id="parameter_table",
                                columns=[
                                    {'id': "added_job", 'name': "job"},
                                    {'id': "added_param_file", 'name': "parameter file"}],
                                data=[],
                                row_deletable=True
                            ),
                               ]), width="auto"),
             ]),
    html.Br(),
    html.Br(),
    dbc.Row(dbc.Card([
            dbc.Button("Add to Job Table",
                        id='add_to_table_button',
                        disabled=False,
                        outline=True,
                        color="success",
                        className="me-1"),
            html.Div(id="job_message_output"),])),
    html.Hr(),
    dbc.Row(dbc.Card(
        dbc.CardBody([
            html.Br(),
            dbc.Button("Export and Start Job",
                       id="job_start_btn",
                       disabled=False,
                       outline=True,
                       color="success",
                       className="me-1"),
            # html.Div(id="trigger", children=0, style=dict(display='none')),
            html.Span(id="job_btn_return",
                      style={"verticalAlign": "middle"})
        ]))),
    html.Br(),
    dbc.Row(dbc.Card(table_layout)),
    html.Br(),
    html.Br(),
    html.Br(),
    html.Hr(),
    html.Div([html.P("Braingeneers@UCSC"),
              html.P("All Rights Reserved")])
])


####---- end of layout ----####


#######################--------------- callback functions ---------------#######################
@callback(
    Output('dropdown', 'options'),
    Input('textarea_filter_uuid', 'value'),
)
def drop_down(value=None):
    return utils.filter_dropdown(search_value=value)


@callback(
    Output('job_table', 'data', allow_duplicate=True),
    Input('batch_job', 'value'),
    State("job_table", "data"),
    State("dropdown", "value"),
    prevent_initial_call=True
)
def update_job_table(input_value, rows, uuid):
    print(f"job input {input_value}")
    if input_value == "Reset":
        print("clear data")
        return []
    elif input_value == "Batch":
        print(f"getting recs for {uuid}")
        recs = wr.list_objects(os.path.join(uuid, "original/data"))
        for i, rec in enumerate(recs):
            # count rows dynamically
            job_info = dict.fromkeys(TABLE_HEADERS)
            job_info["index"] = int(len(rows) + 1)
            job_info["status"] = "ready"
            job_info["uuid"] = uuid  # uuid
            job_info["experiment"] = rec.split("original/data/")[1]
            for h, value in DEFAULT_JOBS["batch"].items():
                job_info[h] = value
            rows.append(job_info)
        print(f"{rows}")
    return rows


@callback(
    Output('job_table', 'data', allow_duplicate=True),
    Output('job_message_output', 'children'),
    Input('add_to_table_button', 'n_clicks'),
    State('checklist_recs', 'value'),
    State("select_jobs", 'value'),
    State("dropdown", "value"),
    State("job_table", "data"),
    State("parameter_table", "data"),
    prevent_initial_call=True
)
def update_job_table_recs(n_clicks, recs, jobs, uuid, rows, param_rows):
    if "add_to_table_button" == ctx.triggered_id:
        # also need to disable this button after clicking
        if len(jobs) == 0:
            return rows, "Please choose a job"
        if len(recs) == 0:
            return rows, "Please choose a recording"
        jobs = sorted(jobs)
        print(f"Selected jobs {jobs}")
        print(f"Selected parameters {param_rows}")
        param_dict = {}
        for p in param_rows:
            param_dict[p["added_job"]] = p["added_param_file"]
        for rec in recs:
            for j in jobs:
                j_ind = jobs.index(j)
                j = int(j)
                job_info = dict.fromkeys(TABLE_HEADERS)
                job_info["index"] = int(len(rows) + 1)
                job_info["status"] = "ready"
                job_info["uuid"] = uuid
                job_info["experiment"] = rec
                param_label = DEFAULT_JOBS["chained"][j]["param_label"]
                if param_label in param_dict:
                    job_info["params"] = f"{param_label}/{param_dict[param_label]}"
                else:
                    job_info["params"] = f"{param_label}/default"    # TODO: make a default parameter file for each job
                for h, value in DEFAULT_JOBS["chained"][j].items():
                    job_info[h] = value
                    if j_ind < len(jobs)-1:
                        job_info["next_job"] = int(job_info["index"]+1)
                rows.append(job_info)
        return rows, None

@callback(
    Output('set_parameter', 'children'),
    Input("select_jobs", 'value'),
    prevent_initial_call=True
    )
def show_parameters_to_job(jobs):
    if len(jobs) == 0:
        return "Please select a job"
    elif len(jobs) > 1:
        return "Please select only one job"
    else:
        # Generate a list of textareas for each selected job
        parameter_fields = []
        parameter_fields.append(
            dbc.Card([
                dbc.Label("Input params file name", html_for=f"params_file_name"),
                dcc.Textarea(id=f"params_file_name", 
                             style={'width': '100%', 'height': 30}),
                html.Br()
                    ]))
        for job in jobs:
            job_params = JOB_PARAMETERS.get(job, [])
            for params in job_params:
                parameter_fields.append(
                    dbc.Card([
                        dbc.Label(params, html_for=f"params_{job}_{params}"),
                        dcc.Textarea(id=f"params_{job}_{params}", style={'width': '100%', 'height': 30}),
                        html.Br()
                    ])
                )
        return parameter_fields

# Change selecting paramters to blocks of RadioItems thus allow user to choose only one paramater for each job 
@callback(
    Output("load_job_param", "children"),   # TODO: reload button to refresh the list.  
    Input("select_jobs", "value"),
    Input ("reload_param_button", "n_clicks"),
    prevent_initial_call=True
)
def load_job_param(jobs, n_clicks):
    if len(jobs) > 0:
        # create RadioItems for each selected job
        display_param_files = []
        for job in jobs:
            job_name = DEFAULT_JOBS["chained"][job]["param_label"]
            param_path = os.path.join(PARAMETER_BUCKET, job_name)
            param_files = wr.list_objects(param_path)
            if len(param_files) > 0:
                display_param_files.append(
                    dbc.Card([
                        f"{job_name}: ",
                        dcc.RadioItems(
                            id={"type": "dynamic-radioitems", "index": f"{job_name}"},
                            options=[{"label": f, "value": f} for f in param_files],
                            value="",
                        ),
                        html.Br()
                    ])
                )
            else:
                display_param_files.append(
                    dbc.Card([
                        f"{job_name}: No parameter file found",
                        html.Br()
                    ])
                )
    return display_param_files

# display the chosen parameter file 
@callback(
        Output("display_param", "value"),
        Input({"type": "dynamic-radioitems", "index": dash.ALL}, "value"),
        State({"type": "dynamic-radioitems", "index": dash.ALL}, "id"),
        prevent_initial_call=True
)
def display_param_file(param_path_list, job_names):
    print(f"params path {param_path_list}")
    print(f"job names {job_names}")
    all_params = {}
    if len(param_path_list) > 0:
        for i in range(len(param_path_list)):
            param_path = param_path_list[i]
            job_type = job_names[i]["index"]
            if param_path.startswith("s3://"):
                with smart_open.open(param_path, 'r') as f:
                    params = json.load(f)
                    print(f"read {params} from {param_path}")
                    # format to human readable text
                    readable_param = utils.readable_keys(params)
                    all_params[job_type] = readable_param

    return utils.format_dict_textarea(all_params)

# display parameter setting before add jobs to table
@callback(
        Output("parameter_table", "data"),
        State("parameter_table", "data"),
        Input({"type": "dynamic-radioitems", "index": dash.ALL}, "value"),
        State({"type": "dynamic-radioitems", "index": dash.ALL}, "id"),

        # State("load_job_param", "value"), # change value to children
        # State("select_jobs", "value"),
        Input("add_param_button", "n_clicks"),
        prevent_initial_call=True
)
def add_param_to_table(data, param_path_list, job_names, n_clicks):
    if "add_param_button" == ctx.triggered_id:
        if len(param_path_list) > 0:
            job_type_exists = [d["added_job"] for d in data]
            for i in range(len(param_path_list)):
                job_type = job_names[i]["index"]
                param_path = param_path_list[i]
                print(f"add params {param_path} for job {job_type}")
                param_file_name = param_path.split("/")[-1]
                if job_type not in job_type_exists:
                    data.append({"added_job": job_type, "added_param_file": param_file_name})
                else:
                    for d in data:
                        if d["added_job"] == job_type:
                            d["added_param_file"] = param_file_name
    return data

    
# save user input parameters to a json file and upload to s3
@callback(
    Output("save_param_button", "disabled"),
    State("set_parameter", "children"),
    State("param_file_name", "value"),
    State("select_jobs", "value"),
    Input("save_param_button", "n_clicks"),
    prevent_initial_call=True
    )
def export_parameter_json(param_fields, param_file_name, job, n_clicks):
    if "save_param_button" == ctx.triggered_id:
        print(n_clicks)
        print(f"job {job}, params {param_fields}, file name {param_file_name}")
        curr_param_file = f"params_{param_file_name}.json"
        param_subbucket = DEFAULT_JOBS["chained"][job[0]]["param_label"]
        s3_param_path = os.path.join(PARAMETER_BUCKET, param_subbucket, curr_param_file)
        # get data from the parameter fields
        param_setting = {}
        for i in range(len(param_fields)):
            if i == 0:
                continue
            param_name = param_fields[i]["props"]["children"][0]["props"]["children"]
            param_value = float(param_fields[i]["props"]["children"][1]["props"]["value"])
            param_label = utils.convert_to_json_key(param_name)
            param_setting[param_label] = param_value
        print(f"{param_setting} for {s3_param_path}")
        try:
            with smart_open.open(s3_param_path, 'w', newline='') as f:
                f.write(json.dumps(param_setting))
            return None
        except Exception as err:
            print(err)
            return None
            # return "Uploading file to s3 failed, please try later"


@callback(
    Output("checklist_recs", "options"),
    Input("dropdown", "value"),
    prevent_initial_call=True
)
def display_recordings(uuid):
    rec_path = os.path.join(uuid, "original/data")
    recs_list = wr.list_objects(rec_path)
    if len(recs_list) > 0:
        options = [rec.split("data/")[1] for rec in recs_list]
        return options
    else:
        return []


@callback(
    Output("checklist_recs", "value"),
    Input("select_recording", "value"),
    State("checklist_recs", "options"),
    prevent_initial_call=True
)
def select_recs(value, recs):
    print(recs)
    if value == "Batch":
        return recs.copy()
    elif value == "Reset":
        return []


@callback(
    Output("textarea_metadata", "value"),
    Input("dropdown", "value"),
    prevent_initial_call=True
)
def show_uuid_metadata(uuid):
    metadata_path = os.path.join(uuid, "metadata.json")
    if metadata_path in wr.list_objects(uuid):
        with smart_open.open(metadata_path, 'r') as md:
            metadata = json.load(md)
        if metadata is not None:
            summary = utils.parse_dict(metadata)
            return utils.format_dict_textarea(summary)
    else:
        return "Metadata not available"


@callback(
    Output('job_start_btn', 'disabled', allow_duplicate=True),
    Output('batch_job', 'value', allow_duplicate=True),
    Input('dropdown', 'value'),
    prevent_initial_call=True
)
def remove_selected_radioitem(value):
    if "dropdown" == ctx.triggered_id:
        return False, None


@callback(
    Output('job_start_btn', 'disabled'),
    Input('job_start_btn', 'n_clicks'),
    State('job_table', 'data'),
    # State('batch_job', 'value'),
    prevent_initial_call=True
)
def disable_job_button(n_clicks, data):
    if "job_start_btn" == ctx.triggered_id:
        print(n_clicks)
        if len(data) > 0:
            return True
        elif len(data) == 0:
            return False


@callback(
    Output("job_btn_return", "children"),
    Output('batch_job', 'value'),
    Output('multipage_data', 'data'),
    Input("job_start_btn", 'n_clicks'),
    State("job_table", "data"),
    State("multipage_data", 'data'),
    prevent_initial_call=True
)
def save_and_start_jobs(n_clicks, data, job_json):
    if len(data) == 0:
        msg = "Add job to start"
        return html.Div(msg), None, job_json
    if "job_start_btn" == ctx.triggered_id and len(data) > 0:
        now = datetime.now()
        curr_dt_csv = now.strftime("%Y%m%d%H%M%S") + '.csv'
        # TODO: send this file by dcc.Store to Status page
        s3_path = os.path.join(SERVICE_BUCKET, curr_dt_csv)
        msg = utils.upload_to_s3(data, s3_path)
        # time.sleep(10) # simulate network lag
        if msg is not None:
            return html.Div(msg), None, job_json
        else:
            job_index = [int(d['index']) for d in data if d['next_job'] == "None"]
            msg = utils.mqtt_start_job(s3_path, job_index)
            if msg is not None:
                return html.Div(msg), None, job_json
            else:
                msg = "Finished Uploading, jobs started"
                print(f"current job csv {job_json}")
                if len(job_json) == 0:
                    job_dict = dict()
                else:
                    job_dict = json.loads(job_json)
                job_dict[curr_dt_csv] = "active"
                job_json = json.dumps(job_dict)
                print(type(job_json), job_json)
                return html.Div(msg), "Reset", job_json

import dash
from dash import html, dcc, callback, Input, Output, State, ctx
from dash import dash_table
import dash_bootstrap_components as dbc
import braingeneers.utils.s3wrangler as wr
import json

# TODO: send over job csv id from job_center page -- Done
# TODO: show real-time job status when an job ID is selected


dash.register_page(__name__)

####----------------------- make page -----------------------####
layout = dbc.Container([
    html.H2("Job Status"),
    # html.Br(),
    html.Hr(),
    html.Div(["Active jobs: ",
              dcc.Checklist(id="checklist_running_jobs",
                            options=[],
                            value=[],
                            )]),

    html.Br(),
    dbc.Button("Clean",
               id='reset_data_button',
               disabled=False,
               outline=True, ),
])


####---- end of layout ----####


#######################--------------- callback functions ---------------#######################
@callback(
    Output("checklist_running_jobs", "options"),
    Input("multipage_data", "data"),
    State("checklist_running_jobs", "options")
)
def show_running_jobs(job_json, options):
    print(type(job_json), f"Get data {job_json}, curr options {options}")
    job_dict = json.loads(job_json)
    if job_dict != {}:
        for k, v in job_dict.items():
            name = "".join(["Job #", k.split(".csv")[0]])
            options.append(name)
    return options


@callback(
    Output("multipage_data", "data", allow_duplicate=True),
    Output("checklist_running_jobs", "options", allow_duplicate=True),
    Input("reset_data_button", "n_clicks"),
    prevent_initial_call=True
)
def clean_stored_data(n_clicks):
    if "reset_data_button" == ctx.triggered_id:
        if n_clicks is not None and n_clicks > 0:
            return str("{}"), []

from io import BytesIO
from shiny import App, ui, render, reactive
from modules.survey import Project
from modules.g import readSheet
from modules.displayr import initializeDeck
import pandas as pd


def read_projects():
    # get the full list of projects with the first row as the column names
    projects_full = pd.DataFrame(readSheet(
        name="https://docs.google.com/spreadsheets/d/1sto8qz1SrVpt4AEWTIqV0YCEPYeUQYiJImugHXpZa78", sheet="2023-24 Sales Tracker"))
    projects_full.columns = projects_full.iloc[0]
    projects_full = projects_full[1:].reset_index(
        drop=True).sort_index(ascending=False)

    # filter on Product = Poll
    projects_full = projects_full[projects_full["Product"] == "Poll"]
    # add column that combines the project number and project description
    projects_full["Project"] = projects_full["Project Number"] + \
        "_" + projects_full["Project Description"]
    return projects_full


projects_full = read_projects()


# navs = ()
# for i in projects_full["Project"].head(50).to_list():
#     print(i)
#     navs = navs + \
#         (ui.nav(i, ui.h1(f"Project {i}"), ui.p(
#             "Full project editing UI here (we can define a shiny module to edit a project and simply call it here.)")),)
# modules are shiny components and they don't share namespaces https://shinylive.io/py/examples/#modules
ContactTab = [
    ui.h1("Contact List"),
    ui.input_file("contactlist", label="Upload Contact List",
                  multiple=True, accept=".csv"),
    ui.output_ui("lists"),

]

DeckTab = [
    ui.h1("Deck"),
    ui.input_file("instrument", label="Upload Instrument",
                  multiple=False, accept=".docx"),
    ui.input_action_button("make_poll", label="Make Poll"),
    ui.output_text_verbatim("out"),
]

tabs = [
    ui.nav("Contact List", *ContactTab),
    ui.nav("Deck", *DeckTab)
]
# Begin UI
app_ui = ui.page_fluid(
    # ui.navset_pill_list(
    #     *navs,
    #     id="nav",
    # ),
    ui.input_select("selected_project", label="Select Project",
                    choices=projects_full["Project"].tolist()),
    ui.navset_tab_card(*tabs, id="nav")
)
# End UI


# Begin Server
def server(input, output, session):
    project: Project = reactive.Value(None)
    list_of_files = reactive.Value([])

    @reactive.Effect
    @reactive.event(input.selected_project)
    def update_project():
        project.set(Project(input.selected_project()))

    @reactive.Effect
    @reactive.event(input.instrument)
    def upload_instrument():
        p: Project = project.get()
        p.upload_file(input.instrument()[0])
        print(p.get_survey())
        project.set(p)

    @reactive.Effect
    @reactive.event(input.contactlist)
    def upload_contactlist():
        p: Project = project.get()
        p.upload_file(input.contactlist()[0])
        project.set(p)
        list_of_files.set(p.contact_lists.raw)
        for file in list_of_files.get():
            print(file)

    @reactive.Effect
    @reactive.event(input.make_poll)
    def make_poll():
        p: Project = project.get()
        df = p.survey.to_dataframe()
        lf = p.survey.to_column_names(as_bytes=True)
        print(df)
        df = BytesIO(df.to_csv(index=False).encode("utf-8"))
        # # write object to csv file
        # with open('test.csv', 'wb') as f:
        #     f.write(df)
        # # write object to csv file
        # with open('test2.csv', 'wb') as f:
        #     f.write(lf)

        initializeDeck(p.name, data=df, colnames=lf,
                       branding="Founders" if "Founders" in p.name else "Coefficient")

    @output
    @render.text()
    def out():
        p: Project = project.get()
        text = p.get_survey()
        return text

    @output
    @render.ui()
    def lists():
        p: Project = project.get()
        return ui.TagList(*[ui.output_text(file.name) for file in list_of_files.get()])
# End Server


# Run App
app = App(app_ui, server)

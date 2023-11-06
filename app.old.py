import datetime
from io import BytesIO
import json
import os
import random
import string
from shiny import App, ui, reactive, render
from modules.displayr import UploadRawData, runScript, updateData, initializeDeck, deleteDeck
from modules.g import deleteFile, getByID, newVersionFolder, readSheet, updateByID, uploadDrive, getDriveFile, checkProject, updateLog
from modules.survey import Survey
from modules.calculate import compare, generateData

import pandas as pd
import re
import weightipy as wp

projects = pd.DataFrame(readSheet())
projects_full = pd.DataFrame(readSheet(
    name="https://docs.google.com/spreadsheets/d/1sto8qz1SrVpt4AEWTIqV0YCEPYeUQYiJImugHXpZa78", sheet="2023-24 Sales Tracker"))
projects_full.columns = projects_full.iloc[0]
# filter on Product = Poll
projects_full = projects_full[projects_full["Product"] == "Poll"]
# add column that combines the project number and project description
projects_full["Project"] = projects_full["Project Number"] + \
    "_" + projects_full["Project Description"]


states = [
    ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
     "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
     "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
     "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
     "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
     "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
     "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming", "National"],
    ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE",
     "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY",
     "LA", "ME", "MD", "MA", "MI", "MN", "MS",
     "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
     "NY", "NC", "ND", "OH", "OK", "OR", "PA",
     "RI", "SC", "SD", "TN", "TX", "UT", "VT",
     "VA", "WA", "WV", "WI", "WY", "US"]
]
# file upload and update button
app_ui = ui.page_fluid(
    ui.input_select("project_name", "Project",
                    choices=projects_full["Project"].sort_index(
                        ascending=False).tolist(),
                    selected="Untracked"),
    ui.navset_tab_card(
        ui.nav("Instrument",
               ui.input_file("instrument_upload", "Doc Upload"),
               ui.output_text_verbatim("status")),
        ui.nav("Alchemer",
               ui.output_text_verbatim("script")),
        ui.nav("IVR",
               ui.input_checkbox("sf", "For Sound Files"),
               ui.output_text_verbatim("ivr")),
        ui.nav("Weighting",
               ui.input_file("weight", "Weight File Upload"),
               ui.input_file("responses", "Data File Upload"),
               ui.input_select("state", "State", states[0], selected=""),
               ui.output_data_frame("weight_vs_responses")
               ),
        ui.nav("Contact List",
               ui.input_file("data1", "File Upload", multiple=True),
               ui.output_text_verbatim("data_file_upload"),
               ui.input_checkbox_group("contacts2", "Lists",
                                       []),
               ui.input_action_button("combineSelected", "Combine Selected"),
               ui.input_action_button("deleteSelected", "Delete Selected"),
               ui.output_ui("contacts"),
               ui.div("Area Codes: ", ui.output_data_frame("area_codes")),
               ui.input_action_button("createText", "Create Text"),
               ui.input_action_button("scrubLL", "Scrub Landlines"),
               ui.input_slider("text_size", "Text Size",
                               min=1, max=100, value=1),
               ui.input_action_button("cutText", "Cut Text List"),
               #    output_widget("contact_list", width="100%", height="1080px"),
               ),
        ui.nav("Manage Deck",
               ui.navset_tab_card(
                   ui.nav("Manage Questions",
                          ui.input_action_button(
                              "addQuestion", "Add Question"),
                          ui.input_action_button(
                              "removeQuestion", "Remove Question"),
                          ui.input_action_button(
                              "updateQuestions", "Update Questions"),
                          ui.output_ui("question_uis"),
                          ),
                   ui.nav("Initialize Deck",
                          ui.input_radio_buttons("branding", "Branding",
                                                 ["Founders", "Coefficient"],
                                                 selected="Coefficient"),
                          ui.input_action_button(
                              "create", "Initialize Deck"),
                          ui.output_ui("deck_preview"),
                          ),
                   ui.nav("Manage Data",
                          ui.input_select("version", "Version", []),
                          ui.input_action_button("newVersion", "New Version"),
                          ui.input_file("alchemer", "Alchemer File Upload"),
                          ui.input_file("broadnet", "Broadnet Upload"),
                          ui.input_action_button(
                              "updateData", "Update Data"),
                          ui.output_data_frame("data_cleaning"),
                          ui.input_slider("data_size", "Data Size",
                                          min=1, max=100, value=1),
                          ui.input_action_button(
                              "cleanData", "Clean Data"),
                          ),

                   ui.nav("Publish",
                          ui.input_action_button(
                              "publish", "Publish for Review"),
                          ui.input_action_button(
                              "publish", "Publish for Delivery"),
                          ),
                   ui.nav("Delete",
                          ui.input_action_button(
                              "delete", "Delete Project"),
                          ),
               ),
               ),
        ui.nav("Notes",
               ui.output_ui("notes")),
    )
)


# Define Module for question
def server(input, output, session):
    # always active
    project = reactive.Value(None)
    survey = reactive.Value(None)
    questions = reactive.Value([])
    contact_files = reactive.Value(None)
    area_codes_list = reactive.Value(None)

    df = reactive.Value(pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]}))

    # activate when on deck manager or script tab
    # or when the instrument is uploaded
    instrument = reactive.Value(None)
    alchemer_script = reactive.Value(None)
    ivr_script = reactive.Value(None)

    preview = reactive.Value(ui.div(ui.h1("Project Preview")))

    # activate when on the contact list or weighting tab
    state = reactive.Value("National")

    @reactive.Effect
    @reactive.event(input.delete)
    def _():
        if project.get() is not None:
            p = project.get()
            if p.keys().__contains__("secret"):
                deleteDeck(p["secret"])
                p["secret"] = ""
                p["url"] = ""
                updateLog(p)
                project.set(p)

    # update the project name
    @reactive.Effect
    @reactive.event(input.project_name)
    def _():
        project.set(checkProject(input.project_name()))
        instrument.set(getDriveFile(project.get(), "instrument"))
        if instrument.get() is not None:
            survey.set(Survey.from_docx(instrument.get()))
            alchemer_script.set(survey.get().to_alchemer_script())
            ivr_script.set(survey.get().to_ivr_script())
        else:
            survey.set(None)
            alchemer_script.set("Please upload an instrument")
            ivr_script.set("Please upload an instrument")
        c = project.get()["versions"].keys()
        c = list(c)
        ui.update_select("version", choices=c)
        qlist = []
        if survey.get() is not None:
            for question in survey.get().questions:
                print(question == question)
                qlist.append(
                    ui.input_text_area(
                        re.sub("question", "_", question.index), question.index +
                        ": ", placeholder=question.question)
                )
                qlist.append(
                    ui.input_select("question_type", "Question Type", [
                        "Screen", "Image", "Vote Method", "Ballot", "SRH", "SRH Method", "SRH Impact", "Job Approval", "Party", "Education", "Race", "Ideology", "Gender"]))
                for answer in question.answers:
                    qlist.append(ui.input_text(
                        "answer", "Answer: ", placeholder=answer))
        questions.set(ui.TagList(qlist))
        clean_list = []

        contact_files_list = list(
            project.get()["contact_lists"].keys())

        contact_files_list.remove("folder")

        for file in contact_files_list:
            if project.get()["name"] in file:
                clean_list.append(file)

        contact_files.set(clean_list)

        contact_files_list = [
            file for file in contact_files_list if file not in clean_list]

        ui.update_checkbox_group(
            "contacts2", choices=contact_files_list, selected=contact_files_list)

        if project.get().keys().__contains__("area_codes"):

            area_codes_list.set(project.get()["area_codes"])

    @reactive.Effect
    @reactive.event(input.createText)
    def _():
        if contact_files.get() is not None:
            cells = getDriveFile(project.get(), "cell_list")
            df_cells = pd.read_csv(BytesIO(cells))
            ui.update_slider("text_size", min=1, max=len(df_cells), value=1)

    @reactive.Effect
    @reactive.event(input.cutText)
    def _():
        if contact_files.get() is not None:
            df = getDriveFile(project.get(), "combined_list")

            df_cells = pd.read_csv(
                BytesIO(df)).drop_duplicates(subset="CellPhone")

            age_groups = df_cells["AgeAppend"].value_counts()
            age_groups = age_groups.to_dict()

            edu_groups = df_cells["EducationAppend"].value_counts()
            edu_groups = edu_groups.to_dict()

            gender_groups = df_cells["GenderAppend"].value_counts()
            gender_groups = gender_groups.to_dict()

            # need to calculate in the future
            age_weight_dict = {
                "18-34": 0.24,
                "35-44": 0.22,
                "45-54": 0.19,
                "55-64": 0.19,
                "65+": 0.16
            }

            gender_weight_dict = {
                "Female": 0.56,
                "Male": 0.44
            }

            education_weight_dict = {
                "HS": 0.37,
                "College": 0.19,
                "Grad+": 0.10,
            }

            targets = {
                "AgeAppend": age_weight_dict,
                "GenderAppend": gender_weight_dict,
                "EducationAppend": education_weight_dict
            }

            scheme = wp.scheme_from_dict(
                targets
            )

            df_weighted = wp.weight_dataframe(
                df_cells, scheme, weight_column="Weight")

            df_weighted = df_weighted.sample(
                n=input.text_size(), weights="Weight")

            df_weighted.to_csv("Resources/Temp.csv", index=False)

            file = {
                "name": project.get()["name"]+"_TextList.csv",
                "datapath": "Resources/Temp.csv"
            }
            uploadDrive(project.get(), file, "text_list")
            contact_files.set(contact_files.get().append(file["name"]))

    @reactive.Effect
    @reactive.event(input.newVersion)
    def _():
        p = project.get()
        newVersionFolder(p)
        ui.update_select("version", choices=list(
            project.get()["versions"].keys()))

    # update instrument case 1

    @reactive.Effect
    @reactive.event(input.instrument_upload)
    def _():
        file = uploadDrive(
            project.get(), input.instrument_upload()[0], "instrument")

        if type(file) == TypeError:
            # shiny alert
            ui.modal_show(ui.modal(
                ui.p(str(file)),
                title="Error",
                easy_close=True,
                fade=True,
            ))
        else:
            with open(input.instrument_upload()[0]["datapath"], "rb") as file:
                instrument.set(file.read())
            survey.set(Survey.from_docx(instrument.get()))

            alchemer_script.set(survey.get().to_alchemer_script())
            ivr_script.set(survey.get().to_ivr_script())

    # update broadnet case 1

    @reactive.Effect
    @reactive.event(input.broadnet)
    def _():
        file = uploadDrive(project.get(), input.broadnet()
                           [0], "broadnet_output", input.version())
        if type(file) == TypeError:
            # shiny alert
            ui.modal_show(ui.modal(
                ui.p(str(file)),
                title="Error",
                easy_close=True,
                fade=True,
            ))

    # update alchemer case 1

    @reactive.Effect
    @reactive.event(input.alchemer)
    def _():
        file = uploadDrive(project.get(), input.alchemer()
                           [0], "alchemer_output", input.version())
        if type(file) == TypeError:
            # shiny alert
            ui.modal_show(ui.modal(
                ui.p(str(file)),
                title="Error",
                easy_close=True,
                fade=True,
            ))

    # update live case 1
    @reactive.Effect
    @reactive.event(input.live)
    def _():
        file = uploadDrive(project.get(), input.live()
                           [0], "live_output", input.version())
        if type(file) == TypeError:
            # shiny alert
            ui.modal_show(ui.modal(
                ui.p(str(file)),
                title="Error",
                easy_close=True,
                fade=True,
            ))

    @reactive.Effect
    @reactive.event(input.data1)
    def _():
        file = uploadDrive(project.get(), input.data1()[0], "raw_data")
        if type(file) == TypeError:
            # shiny alert
            ui.modal_show(ui.modal(
                ui.p(str(file)),
                title="Error",
                easy_close=True,
                fade=True,
            ))
        contact_files_list = list(
            project.get()["contact_lists"].keys())
        contact_files_list.remove("folder")

        ui.update_checkbox_group(
            "contacts2", choices=contact_files_list, selected=contact_files_list)

    @reactive.Effect
    @reactive.event(input.deleteSelected)
    def _():
        if input.contacts2():
            for file in input.contacts2():
                deleteFile(project.get(), file)
            project.set(checkProject(input.project_name()))
            contact_files_list = list(
                project.get()["contact_lists"].keys())
            contact_files_list.remove("folder")
            for file in contact_files_list:
                print(file)
                print(project.get()["name"])
                if project.get["name"] in file:

                    contact_files_list.remove(file)
            ui.update_checkbox_group(
                "contacts2", choices=contact_files_list, selected=contact_files_list)

    @reactive.Effect
    @reactive.event(input.combineSelected)
    def _():
        if input.contacts2():
            files = []
            for file in input.contacts2():
                files.append(file)
            if len(files) > 0:
                if len(files) == 1:
                    file = files[0]
                    print(file)
                    file = getDriveFile(project.get(), file)

                    df = pd.read_csv(BytesIO(file))
                else:
                    file = getDriveFile(project.get(), files[0])
                    df = pd.read_csv(BytesIO(file))
                    for i in range(1, len(files)):
                        print(files[i])
                        file = getDriveFile(project.get(), files[i])
                        df2 = pd.read_csv(BytesIO(file))
                        df = pd.concat([df, df2])
                df.rename(columns={
                    "Voters_StateVoterID": "ID",
                    "Voters_FirstName": "FirstName",
                    "Voters_LastName": "LastName",
                    "VoterTelephones_LandlineUnformatted": "Phone",
                    "VoterTelephones_CellPhoneUnformatted": "CellPhone",
                    "CommercialData_Education": "EducationAppend",
                    "Voters_Gender": "GenderAppend",
                    "EthnicGroups_EthnicGroup1Desc": "RaceAppend",
                    "Parties_Description": "PartyAppend",
                    "Voters_Age": "AgeAppend",
                    "County": "County",
                    "Urban_Rural_Category": "UrbanRural",
                    "CommercialData_EstimatedHHIncome": "HHIncome",
                    "Designated_Market_Area__DMA_": "DMA",
                    "US_Congressional_District": "CongressionalDistrict",
                    "State_House_District": "StateHouseDistrict",
                    "State_Senate_District": "StateSenateDistrict",
                    "Residence_Addresses_AddressLine": "Address",
                    "Residence_Addresses_ExtraAddressLine": "AddressLine2",
                    "Residence_Addresses_City": "City",
                    "Residence_Addresses_Zip": "Zip",
                    "State": "State",
                    "Voters_Active": "RegistrationStatus",
                }, inplace=True)
                cols = ["ID",
                        "FirstName",
                        "LastName",
                        "Phone",
                        "CellPhone",
                        "EducationAppend",
                        "RaceAppend",
                        "PartyAppend",
                        "GenderAppend",
                        "AgeAppend",
                        "County",
                        "UrbanRural",
                        "HHIncome",
                        "DMA",
                        "CongressionalDistrict",
                        "StateHouseDistrict",
                        "StateSenateDistrict",
                        "Address",
                        "AddressLine2",
                        "City",
                        "Zip",
                        "State",
                        "RegistrationStatus",]
                for column_name in df.columns:
                    if column_name.startswith("General_\d\d\d\d") or column_name.startswith("Presidential_Primary_\d\d\d\d") or column_name.startswith("Primary_\d\d\d\d"):
                        cols.append(column_name)
                df = df[cols]

                # for each row sum the number of times a voter has voted in the last 4 elections
                # with the data format of 1 = voted, 0 = did not vote in each column for each election
                # if the column name starts with General, Presidential_Primary, or Primary
                df["Last4Generals"] = df.apply(
                    lambda row: row.filter(regex="General_\d\d\d\d").sum(), axis=1)
                df["Last4Primaries"] = df.apply(
                    lambda row: row.filter(regex="Primary_\d\d\d\d").sum(), axis=1)

                def age_match(x):
                    if x < 35:
                        return "18-34"
                    elif x < 45:
                        return "35-44"
                    elif x < 55:
                        return "45-54"
                    elif x < 65:
                        return "55-64"
                    elif x >= 65:
                        return "65+"

                def education_match(x):
                    match x:
                        case "HS Diploma - Extremely Likely":
                            return "HS"
                        case "Some College - Extremely Likely":
                            return "HS"
                        case "HS Diploma - Likely":
                            return "HS"
                        case "Some College - Likely":
                            return "HS"
                        case "Bach Degree - Extremely Likely":
                            return "College"
                        case "Bach Degree - Likely":
                            return "College"
                        case "Grad Degree - Extremely Likely":
                            return "Grad+"
                        case "Grad Degree - Likely":
                            return "Grad+"
                        case _:
                            return None

                df["AgeAppend"] = df["AgeAppend"].apply(
                    lambda x: age_match(x)
                )

                df["GenderAppend"] = df["GenderAppend"].apply(
                    lambda x: "Male" if x == "M" else "Female")

                df["EducationAppend"] = df["EducationAppend"].apply(
                    lambda x: education_match(x))

                print(df["AgeAppend"])

                df["DataSource"] = "L2"
                # assign a random unique four letter string to each row
                df["URL"] = df.apply(
                    lambda row: ''.join(random.choice(string.ascii_letters) for i in range(4)), axis=1)

                # subset the dataframe to file of unique Cells and Landlines
                df_cell = df[["CellPhone", "URL", "FirstName",
                              "LastName", "DataSource", "ID"]]
                df_cell = df_cell.drop_duplicates(subset="CellPhone")

                df_landline = df[["Phone", "URL", "FirstName",
                                  "LastName", "DataSource", "ID"]]
                df_landline = df_landline.drop_duplicates(subset="Phone")

                # subset the dataframe to file of Area Codes
                df_cell_area_codes = df_cell[["CellPhone"]]
                df_cell_area_codes = df_cell_area_codes["CellPhone"].apply(
                    lambda x: str(x)[:3])
                # count the frequency of each area code
                df_cell_area_codes = df_cell_area_codes.value_counts()
                df_cell_area_codes = df_cell_area_codes.to_dict()

                df_landline_area_codes = df_landline[["Phone"]]
                df_landline_area_codes = df_landline_area_codes["Phone"].apply(
                    lambda x: str(x)[:3])
                # count the frequency of each area code
                df_landline_area_codes = df_landline_area_codes.value_counts()
                df_landline_area_codes = df_landline_area_codes.to_dict()

                # add area_codes to the project log
                p = project.get()
                p["area_codes"] = {
                    "cell": df_cell_area_codes,
                    "landline": df_landline_area_codes
                }
                updateLog(p)
                project.set(p)
                area_codes_list.set(p["area_codes"])

                # upload each df to drive
                df.to_csv("Resources/Temp.csv", index=False)
                file = {
                    "name": project.get()["name"]+"_CombinedContactList.csv",
                    "datapath": "Resources/Temp.csv"
                }

                uploadDrive(project.get(), file,
                            "combined_list")
                df_cell.to_csv("Resources/Temp.csv", index=False)

                file["name"] = project.get()["name"]+"_CellPhones.csv"
                uploadDrive(project.get(), file,
                            "cell_list")

                df_landline.to_csv("Resources/Temp.csv", index=False)
                file["name"] = project.get()["name"]+"_LandLines.csv"
                uploadDrive(project.get(), file,
                            "landline_list")

                project.set(checkProject(input.project_name()))
                contact_files_list = list(
                    project.get()["contact_lists"].keys())
                clean_list = []

                contact_files_list.remove("folder")
                for file in contact_files_list:
                    if file.startswith(project.get()["name"]):
                        clean_list.append(file)
                contact_files.set(clean_list)
                contact_files_list = [
                    file for file in contact_files_list if file not in clean_list]
                ui.update_checkbox_group(
                    "contacts2", choices=contact_files_list, selected=contact_files_list)

            else:
                contact_files.set(None)

    @reactive.Effect
    @reactive.event(input.create)
    def _():
        if survey.get() is not None:
            if project.get().keys().__contains__("url") and project.get()["url"] != "":
                iframe = '<iframe src="%s" width="1000" height="600"></iframe>' % project.get()[
                    "url"]
                preview.set(ui.div(
                    ui.h1("Project Preview"),
                    ui.HTML(iframe)))
            else:

                data = survey.get().to_dataframe()
                labels = survey.get().to_column_names()
                xnames = survey.get().to_xnames()
                data = BytesIO(data.to_csv(index=False).encode())
                labels = BytesIO(labels.to_csv(index=False).encode())
                xnames = BytesIO(xnames.to_csv(index=False).encode())

                branding = input.branding()

                url, secret = initializeDeck(input.project_name(), data,
                                             labels, xnames, branding=branding)

                iframe = '<iframe src="%s" width="1000" height="600"></iframe>' % url
                preview.set(ui.div(
                    ui.h1("Project Preview"),
                    ui.HTML(iframe)))

                # update project log
                log = project.get()
                log["url"] = url
                log["secret"] = secret
                updateLog(log)
                project.set(log)
        else:
            preview.set(ui.div(ui.h1("Project Preview"),
                               ui.h2("Please upload an instrument")))

    @reactive.Effect
    @reactive.event(input.scrubLL)
    def _():
        # download LandLine file from drive
        # Check call log for each file in the same state
        # download all files in the same state or national
        # that were called in the last 30 days
        # check each file for duplicate phone numbers
        # delete duplicate phone numbers from the Landline file
        # upload the scrubbed file back to drive
        # and update the call log with the date, state, and file id
        project = project.get()
        if project["contact_lists"].keys().__contains__("landline_list"):
            file = getDriveFile(project, "landline_list")
            df = pd.read_csv(BytesIO(file))
            scrubLog = getByID("1eYVUbzn7iOaJgwsgg33b5WRR4NOkBzv6")
            # read json from raw buffer
            scrubLog = json.loads(scrubLog)

            scrubDF = pd.DataFrame()
            if project["name"]+"_LandLines.csv" in scrubLog.keys():
                # alert that the file has already been scrubbed and ask if the user wants to continue
                # if yes, continue
                # if no, return
                return
            for file in scrubLog:
                if file["state"] == project["state"]:
                    if file["date"] > datetime.now() - datetime.timedelta(days=30):
                        file = getByID(file["id"])
                        df2 = pd.read_csv(BytesIO(file), usecols=["Phone"])
                        scrubDF = scrubDF.append(df2)
                elif file["state"] == "US":
                    if file["date"] > datetime.now() - datetime.timedelta(days=30):
                        file = getByID(file["id"])
                        df2 = pd.read_csv(BytesIO(file), usecols=["Phone"])
                        scrubDF = scrubDF.append(df2)
            df = df[~df["Phone"].isin(scrubDF["Phone"])]

            scrubLog[project["name"]+"_LandLines.csv"] = {
                "date": datetime.now(),
                "state": project["state"],
                "id": project["contact_lists"]["landline_list"]
            }

            # update the scrub log
            # write to json file
            with open("Resources/scrub_log.json", "w") as file:
                json.dump(scrubLog, file)
            updateFile = {}
            updateFile["datapath"] = "Resources/scrub_log.json"
            updateFile["name"] = "scrub_log.json"

            updateByID("1eYVUbzn7iOaJgwsgg33b5WRR4NOkBzv6", updateFile)
            os.remove("Resources/scrub_log.json")

            df.to_csv("Resources/Temp.csv", index=False)
            file = {
                "name": project["name"]+"_LandLines.csv",
                "datapath": "Resources/Temp.csv"
            }
            uploadDrive(project, file, "landline_list")

    @reactive.Effect
    @reactive.event(input.updateData)
    def _():
        if project.get() is not None:
            if input.version() is not None:
                print(input.version())
                alchemer = project.get()[
                    "versions"][input.version()]["alchemer"]
                broadnet = project.get()[
                    "versions"][input.version()]["broadnet"]
                # live = project.get()["versions"][input.version()]["live"]
                contact_list = project.get()["contact_lists"]["combined_list"]

                alchemer = getDriveFile(project.get(), alchemer)
                broadnet = getDriveFile(project.get(), broadnet)
                # live = getDriveFile(project.get(), live)
                contact_list = getDriveFile(project.get(), contact_list)

                data, labels = generateData(alchemer=alchemer, broadnet=broadnet,
                                            contactlist=contact_list)
                ui.update_slider("data_size", min=1, max=len(data), value=1)

                df.set(data)

                data.to_csv("Resources/data.csv", index=False)
                labels.to_csv("Resources/labels.csv", index=False)

    @output
    @render.data_frame
    def data_cleaning():
        if input.data1():
            return df.get()

        # if input.project_name():
        #     project_secret = project.get()["secret"]
        #     name = input.project_name()
        #     if input.data():
        #         file = getDriveFile(project_secret, "data_output")
        #         UploadRawData("TemplateData_Flex.csv", file, name+"_All.csv")
        #     if input.columns():
        #         file = getDriveFile(project_secret, "column_names")
        #         UploadRawData("TemplateData_RepublicanPrimary_ColNames.csv", file,
        #                       name+"_ColNames.csv")
        #     if input.xnames():
        #         file = getDriveFile(project_secret, "xnames")
        #         UploadRawData("TemplateData_Flex_Xnames.csv",
        #                       file, name+"_Xnames.csv")
        #     updateData(project_secret)
        #     with open('Resources/tidy.QScript', 'r') as file:
        #         qscript = file.read()
        #         # append functions to qscript
        #         qscript += "methodology_page();"
        #         runScript(project_secret, qscript)
        #     return "Success"
        # else:
        #     return "Please initialize deck"
    @output
    @render.text
    def project_url():
        if project.get() is not None:
            if project.get().keys().__contains__("url"):
                return project.get()["url"]
            else:
                return "Please initialize deck"

    @output
    @render.ui
    def deck_preview():
        return preview.get()

    @output
    @render.data_frame
    def weight_vs_responses():
        if input.weight():
            if input.responses():
                file = input.weight()[0]
                if file["name"].endswith(".csv"):
                    df = compare(file["datapath"],
                                 input.responses()[0]["datapath"])
                    return df
                else:
                    df = pd.DataFrame(
                        {"please": ["upload a weight file as csv"]})
                    return df
            else:
                df = pd.DataFrame({"please": ["upload a response file"]})
                return df
        else:
            df = pd.DataFrame({"please": ["upload a weight file"]})
            return df

    @output
    @render.text
    @reactive.event(input.project_name)
    def script():
        if survey.get() is None:
            return "Please upload an instrument"
        else:
            return survey.get().to_alchemer_script()

    @output
    @render.text
    def script():
        return alchemer_script.get()

    @output
    @render.text
    def ivr():
        return ivr_script.get()

    @output
    @render.data_frame
    @reactive.event(input.project_name)
    def template_output():
        return survey.get().to_data_frame()

    @output
    @render.ui
    @reactive.event(input.project_name)
    def notes():
        notes = []
        for item in project.get().keys():
            notes.append(ui.output_text_verbatim("project_name", item))
        return ui.TagList(notes)

    @output
    @render.ui
    def contacts():
        file_list = ""
        for file in contact_files.get():
            file_list += "<li><a href='https://drive.google.com/file/d/" + \
                project.get()["contact_lists"][file] + \
                "/view?usp=sharing'>" + file + "<a></li>"

        return ui.HTML(file_list)

    @output
    @render.data_frame
    def area_codes():
        print("fired")
        lists = pd.DataFrame()

        cells = []
        lls = []
        if area_codes_list.get() is not None:
            counts = area_codes_list.get()
            print(counts["landline"])

            counts_cell = pd.DataFrame().from_dict(
                counts["cell"], orient="index")
            counts_ll = pd.DataFrame().from_dict(
                counts["landline"], orient="index")

            for i in range(0, 4):
                cells.append(counts_cell.index[i])
                lls.append(counts_ll.index[i])

        lists["Cell Area Codes"] = cells
        lists["LL Area Codes"] = lls
        print(lists)
        return lists


# create the app
app = App(app_ui, server=server)

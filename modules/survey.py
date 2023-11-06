import datetime
import json
import re
from io import BytesIO
from typing import Dict, List, Optional
import pyreadstat
import docx
import pandas as pd
from .calculate import generateData

from .g import File, Folder, getLogs, updateLog


class Question:
    def __init__(self, question: str = "Is this a question?", question_type: str = "Generic", answers: List[str] = ["Yes", "No"], index: str = "0"):
        self.question = question
        if question_type == "Ballot" and len(answers) == 3:
            self.question_type = "Head to Head"
        elif question_type == "Informed Ballot" and len(answers) == 3:
            self.question_type = "Informed Head to Head"
        else:
            self.question_type = question_type
        self.answers = answers
        self.index = index
        match self.question_type:
            case "Ballot":
                self.sub_type = re.findall(
                    "^if the (.+) were held today", self.question, re.IGNORECASE)[0]
            case "Head to Head":
                self.sub_type = re.findall(
                    "^if the (.+) were held today", self.question, re.IGNORECASE)[0]
            case "Image":
                self.sub_type = re.findall(
                    "what is your opinion of (.+)?", self.question, re.IGNORECASE)[0]
            case "AB Test":
                self.sub_type = re.findall("Candidate A. ", answers[0], re.IGNORECASE)[
                    0] + re.findall("Candidate B. ", answers[1], re.IGNORECASE)[0]
            case _:
                self.sub_type = None

    def __str__(self) -> str:
        return self.question + "\n" + "\n".join(self.answers) + "\n"

    def __dict__(self) -> dict:
        return {
            "question": self.question,
            "question_type": self.question_type,
            "answers": self.answers,
            "index": self.index
        }

    def __eq__(self, __value: object) -> bool:
        if type(__value) == type(self):
            other = __value
        elif type(__value) == type(dict):
            other = Question.from_dict(__value)
        else:
            return False

        if re.sub(r'[^\w]', '', self.question.lower()) == re.sub(r'[^\w]', '', other.question.lower()):
            return True
        if self.question_type == other.question_type and self.sub_type == other.sub_type:
            return True
        return False

    def __len__(self) -> int:
        return len(self.answers)

    def to_dict(self) -> dict:
        return self.__dict__()

    @classmethod
    def from_dict(cls, dict: dict):
        return cls(dict["question"], dict["question_type"], dict["answers"], dict["index"])

    # def to_shiny_module(self) -> str:
    #    return "question_ui(custom_label = \"" + self.index + "\")"


class Survey:
    def __init__(self, title: str, date: Optional[str], n: Optional[int], questions: list[Question]):
        self.title = title
        self.date = date
        self.n = n
        self.questions = questions

    def __str__(self) -> str:
        string = ""
        for question in self.questions:
            string += question.question_type + ": " + str(question)
        return self.title + "\n" + self.date + "\n" + self.n + "\n" + string

    def __dict__(self) -> dict:
        dict = {
            "title": self.title,
            "date": self.date,
            "n": self.n,
            "questions": {

            }
        }
        for question in self.questions:
            dict["questions"][question.index] = question.to_dict()

        return {
            "title": self.title,
            "date": self.date,
            "n": self.n,
            "questions": self.questions.to_dict()
        }

    def __len__(self) -> int:
        return len(self.questions)

    def to_dict(self) -> dict:
        return self.__dict__()

    def __iter__(self):
        for question in self.questions:
            yield question

    def __getitem__(self, index):
        return self.questions[index]

    def to_spss_metadata(self):
        # TODO: Create SPSS metadata
        return self.to_column_names()["Full"]

    @classmethod
    def from_dict(cls, dict: dict):
        questions = []
        for question in dict["questions"]:
            questions.append(Question.from_dict(question))
        return cls(dict["title"], dict["date"], dict["n"], questions)

    @classmethod
    def from_docx(cls, file: File):
        if file is None:
            print("Docx file not provided")
            return None
        print("\n"*5)
        print("Creating survey from docx")
        print("\n"*5)

        doc = docx.Document(file())
        questions = []
        for para in doc.paragraphs:
            para.text = re.sub(" – ", "-", para.text)
            para.text = re.sub("’", "'", para.text)
            para.text = re.sub("“", '"', para.text)
            para.text = re.sub("”", '"', para.text)
            para.text = re.sub("\n", "", para.text)

            if para._element.get_or_add_pPr().get_or_add_numPr().numId is not None:
                if para._element.get_or_add_pPr().get_or_add_numPr().get_or_add_ilvl().val == 0:
                    match RegexMatch(para.text):
                        case "(^do you (plan|intend) to vote)|(\. do you (plan|intend) to vote)":
                            q_type = "Screen"
                        case "who would you vote for your (second|2nd) choice":
                            q_type = "2nd Choice"
                        case "what is your opinion of":
                            q_type = "Image"
                        case "how do you (plan|intend) to vote":
                            q_type = "Vote Method"
                        case "knowing what you know now":
                            q_type = "Informed Ballot"
                        case "who would you vote for":
                            q_type = "Ballot"
                        case "have you recently seen, read(|,) or heard":
                            q_type = "SRH"
                        case "see, read(|,) or hear":
                            q_type = "SRH Method"
                        case "If you have recently seen, read(|,) or heard":
                            q_type = "SRH Impact"
                        case "is doing (his|her) job":
                            q_type = "Job Approval"
                        case "(which|what) party do you most align with":
                            q_type = "Party"
                        case "what is your age":
                            q_type = "Age"
                        case "(what|which) ideology is most in line with your views":
                            q_type = "Ideology"
                        case "are you male or female":
                            q_type = "Gender"
                        case "what is the highest level of education you have (completed|attained) so far":
                            q_type = "Education"
                        case "what is your race":
                            q_type = "Race"
                        case "which of the following candidates would you be more likely to vote for":
                            q_type = "AB Test"
                        case "does knowing this":
                            q_type = "Message"

                        case _:
                            q_type = "Generic"
                    if re.search("Screen|Ideology|Gender|Education|Age|Party|Race", q_type):
                        index = q_type
                    else:
                        index = "Q"+str(len(questions))
                    questions.append(Question(para.text, q_type, [], index))
                elif para._element.get_or_add_pPr().get_or_add_numPr().get_or_add_ilvl().val == 1:
                    questions[-1].answers.append(para.text)
            elif re.search("do you (plan|intend) to vote", para.text, flags=re.IGNORECASE):
                questions.append(Question(para.text, "Screen", [], "Screen"))
        return cls("TITLE", "DATE", "N", questions)

    def to_dataframe(self, as_bytes=True) -> pd.DataFrame:
        df = pd.DataFrame()
        for question in self.questions:
            fill = [""] * (10-len(question.answers))
            df[question.index] = question.answers + fill
            df[question.index] = df[question.index].transform(
                lambda x: re.sub(" \(random order\)", "", str(x), flags=re.IGNORECASE))
            match question.question_type:
                case "Race":
                    df[question.index] = df[question.index].transform(
                        lambda x: re.sub("african american", "Black", str(x), flags=re.IGNORECASE))
                case "Ideology":
                    df[question.index] = df[question.index].transform(
                        lambda x: re.sub("conservative", "Conserv.", str(x), flags=re.IGNORECASE))
                case "Education":
                    df[question.index] = df[question.index].transform(
                        lambda x:
                        "HS" if re.search("high school", str(x), flags=re.IGNORECASE) else "Grad+" if re.search("grad(|uate) degree or higher", str(x), flags=re.IGNORECASE) else str(x))
                case "Age":
                    df[question.index] = df[question.index].transform(
                        lambda x: re.sub("65 or older", "65+", str(x), flags=re.IGNORECASE))

        df["X1"] = df["Gender"]
        df["X2"] = df["Education"]
        df["X3"] = df["Ideology"]
        df["X4"] = df["Age"]
        df["X5"] = df["Race"]
        df["X6"] = [1, 2, 3, 4, 0] + [""] * 5
        if "Party" in df.columns:
            df["X7"] = df["Party"]
        else:
            df["X7"] = [""] * 10
        df["X8"] = ["DMA1", "DMA2", "DMA3", "DMA4", "DMA5"] + [""] * 5
        df["X9"] = ["CD1", "CD2", "CD3", "CD4", "CD5"] + [""] * 5
        print(as_bytes)
        return df

    def to_column_names(self, as_bytes: bool = False) -> pd.DataFrame:
        generic = ["ID", "Method", "Screen"]
        label = ["ID", "Method", "Screen"]
        full = ["ID", "Method", "Screen"]
        for question in self.questions:
            if question.question_type == "Screen":
                full[2] = question.question
                continue
            generic.append(question.index)
            label.append(question.question_type)
            full.append(question.question)
        return BytesIO(pd.DataFrame({
            "Generic": generic,
            "Label": label,
            "Full": full
        }).to_csv(index=False).encode())
        if as_bytes:
            BytesIO(pd.DataFrame({
                "Generic": generic,
                "Label": label,
                "Full": full
            }).to_csv(index=False).encode())
        else:
            return pd.DataFrame({
                "Generic": generic,
                "Label": label,
                "Full": full
            })

    def to_xnames(self) -> pd.DataFrame:
        return pd.DataFrame({
            "XX": ["X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9"],
            "xLabel": ["Gender", "Education Level", "Ideology", "Age", "Race", "Last 4 Generals", "Party", "DMA", "CD"]
        })

    def to_ivr_script(self) -> str:
        string = ""
        for question in self.questions:
            string += question.question
            string += "\n"
            for i, answer in enumerate(question.answers):
                string += "For " + answer + " press "+str(i+1) + "\n"
            string += "\n"
        return string

    def to_alchemer_script(self) -> str:
        string = ""
        for question in self.questions:
            string += question.question
            for answer in question.answers:
                string += "\n() " + answer
            string += "\n\n"
        return string

    def to_qscript(self) -> str:
        string = ""
        for question in self.questions:
            if question.question_type == "Screen":
                continue
            string += "toPage(" + question.type + ", " + \
                str(len(question.answers)) + ", " + question.index + ")\n"
        return string

    def match_questions(self, other) -> list:
        q_match = []
        for question in self.questions:
            for other_question in other.questions:
                if other_question == question:
                    q_match.append((question, other_question))
        return q_match


class ContactSet(Folder):
    driveID: str = None
    combined: File = None
    cells: File = None
    landlines: File = None
    raw: List[File] = None

    def __init__(self, lists=List[File], parent: str = None, driveID: str = None):
        self.l2_files = []
        self.i360_files = []
        self.misc = []
        super().__init__("Contact Lists", driveID=driveID, parent=parent)
        for list in lists:
            if "CombinedContactList.csv" in list.name:
                self.combined = list
            elif "CellPhones.csv" in list.name:
                self.cells = list
            elif "LandLines.csv" in list.name:
                self.landlines = list
            elif re.search("^X_[A-Z0-9]{9}", list.name):
                self.l2_files.append(list)
            elif re.search("-[a-z0-9]{32}.csv", list.name):
                self.i360_files.append(list)
            else:
                self.misc.append(list)

        self.raw = self.l2_files + self.i360_files + self.misc

    def __dict__(self):
        dict = {
            "name": "Contact Lists",
            "driveID": self.driveID,
            "parent": self.parent,
        }

        if self.combined is not None:
            dict["combined"] = self.combined.to_dict()
        if self.cells is not None:
            dict["cells"] = self.cells.to_dict()
        if self.landlines is not None:
            dict["landlines"] = self.landlines.to_dict()

        for file in self.raw:
            dict[file.name] = file.to_dict()
        return dict

    def to_dict(self):
        return self.__dict__()

    @classmethod
    def from_dict(cls, contact: dict):

        if "driveID" in contact.keys():
            cs = cls([], parent=contact["parent"] if "parent" in contact.keys()
                     else None, driveID=contact["driveID"])
        else:
            KeyError("Contact Set does not have a driveID")
        if "combined" in contact.keys():
            cs.combined = File.from_dict(contact["combined"])
        if "cells" in contact.keys():
            cs.cells = File.from_dict(contact["cells"])
        if "landlines" in contact.keys():
            cs.landlines = File.from_dict(contact["landlines"])
        for key in contact.keys():
            if key not in ["driveID", "combined", "cells", "landlines", "parent", "name"]:
                cs.raw.append(File.from_dict(contact[key]))
                if re.search("^X_[A-Z0-9]{9}", key):
                    cs.l2_files.append(File.from_dict(contact[key]))
                elif re.search("-[a-z0-9]{32}.csv", key):
                    cs.i360_files.append(File.from_dict(contact[key]))
                else:
                    cs.misc.append(File.from_dict(contact[key]))
        return cs

    # write a generator to iterate through all the files in the contact set
    def __iter__(self):
        for file in self.raw:
            yield file

    def upload_file(self, file: dict | BytesIO):
        if file is None:
            print("No file provided")
            return None
        if type(file) == BytesIO:
            file = File("file", content=file, parent=self.driveID)
        elif type(file) == dict:
            file["parent"] = self.driveID

        if "CombinedContactList.csv" in file["name"]:
            if self.combined is not None:
                file["to_replace"] = self.combined.driveID
            file = File.from_dict(file)
            self.combined = file
        elif "CellPhones.csv" in file["name"]:
            if self.cells is not None:
                file["to_replace"] = self.cells.driveID
            file = File.from_dict(file)
            self.cells = file
        elif "LandLines.csv" in file["name"]:
            if self.landlines is not None:
                file["to_replace"] = self.landlines.driveID
            file = File.from_dict(file)
            self.landlines = file
        else:
            if re.search("^X_[A-Z0-9]{9}", file["name"]):
                self.l2_files.append(file)
                self.raw.append(file)
            elif re.search("-[a-z0-9]{32}.csv", file["name"]):
                self.i360_files.append(file)
                self.raw.append(file)
            else:
                self.misc.append(file)
            self.raw.append(file)

    def get(self, name: str, bytes: bool = False):
        if name == "cells":
            file = self.cells()
        elif name == "landlines":
            file = self.landlines()
        elif name == "combined":
            file = self.combined()
        else:
            return None
        if bytes:
            return file
        else:
            return pd.read_csv(file)


class DataSet(Folder):
    name: str = None
    files: List[File] = None
    supporting_documents: Folder = None
    input_files: Folder = None
    alchemer_input: File = None
    broadnet_input: File = None
    data_output: File = None
    column_output: File = None
    xnames_output: File = None

    def __init__(self, name: str, parent: str = None):
        super().__init__(name, parent=parent)
        self.supporting_documents = Folder(
            "Supporting Documents", parent=self.driveID)
        self.input_files = Folder("Input Files", parent=self.driveID)
        self.name = name

    def __dict__(self):
        dict = {
            "name": self.name,
            "driveID": self.driveID,
            "files": self.files,
            "supporting_documents": self.supporting_documents.to_dict(),
            "input_files": self.input_files.to_dict(),
        }
        if self.alchemer_input is not None:
            dict["alchemer_input"] = self.alchemer_input.to_dict()
        if self.broadnet_input is not None:
            dict["broadnet_input"] = self.broadnet_input.to_dict()
        if self.data_output is not None:
            dict["data_output"] = self.data_output.to_dict()
        if self.column_output is not None:
            dict["column_output"] = self.column_output.to_dict()
        if self.xnames_output is not None:
            dict["xnames_output"] = self.xnames_output.to_dict()

        return dict

    def to_dict(self):
        return self.__dict__()

    def upload_file(self, file: dict | BytesIO):
        if file is None:
            print("No file provided")
            return None
        if type(file) == BytesIO:
            file = File("file", content=file, parent=self.driveID)
        elif type(file) == dict:
            if "SurveyExport" in file["name"]:
                if self.alchemer_input is not None:
                    file["to_replace"] = self.alchemer_input.driveID
                file["parent"] = self.input_files.driveID
                self.alchemer_input = File.from_dict(file)
            elif "response_data" in file["name"]:
                if self.broadnet_input is not None:
                    file["to_replace"] = self.broadnet_input.driveID
                file["parent"] = self.input_files.driveID
                self.broadnet_input = File.from_dict(file)
            elif "All.csv" in file["name"]:
                if self.data_output is not None:
                    file["to_replace"] = self.data_output.driveID
                file["parent"] = self.supporting_documents.driveID
                self.data_output = File.from_dict(file)
            elif "Colnames.csv" in file["name"]:
                if self.column_output is not None:
                    file["to_replace"] = self.column_output.driveID
                file["parent"] = self.supporting_documents.driveID
                self.column_output = File.from_dict(file)
            elif "Xnames.csv" in file["name"]:
                if self.xnames_output is not None:
                    file["to_replace"] = self.xnames_output.driveID
                file["parent"] = self.supporting_documents.driveID
                self.xnames_output = File.from_dict(file)
            else:
                file["parent"] = self.supporting_documents.driveID
                self.files.append(File.from_dict(file))

    def get(self, name: str, bytes: bool = False):
        if name == "alchemer_input":
            file = self.alchemer_input()
        elif name == "broadnet_input":
            file = self.broadnet_input()
        elif name == "data_output":
            file = self.data_output()
        elif name == "column_output":
            file = self.column_output()
        elif name == "xnames_output":
            file = self.xnames_output()
        else:
            return None
        if bytes:
            return file
        else:
            return pd.read_csv(file)

    @classmethod
    def from_dict(cls, dict: dict):
        dataset = cls(dict["name"])
        dataset.driveID = dict["driveID"]
        dataset.files = dict["files"]
        dict["supporting_documents"]["name"] = "Supporting Documents"
        dict["supporting_documents"]["parent"] = dict["driveID"]
        dataset.supporting_documents = Folder.from_dict(
            dict["supporting_documents"])
        dict["input_files"]["name"] = "Input Files"
        dict["input_files"]["parent"] = dict["driveID"]
        dataset.input_files = Folder.from_dict(dict["input_files"])
        if "alchemer_input" in dict.keys():
            dataset.alchemer_input = File.from_dict(dict["alchemer_input"])
        if "broadnet_input" in dict.keys():
            dataset.broadnet_input = File.from_dict(dict["broadnet_input"])
        if "data_output" in dict.keys():
            dataset.data_output = File.from_dict(dict["data_output"])
        if "column_output" in dict.keys():
            dataset.column_output = File.from_dict(dict["column_output"])
        if "xnames_output" in dict.keys():
            dataset.xnames_output = File.from_dict(dict["xnames_output"])
        return dataset

    # write a generator to iterate through all the files in the dataset

    def __iter__(self):
        for file in self.files:
            yield file


class Project:
    name: str = None
    folder: Folder = None
    instrument: File = None
    survey: Survey = None
    contact_lists: ContactSet = None
    versions: Dict[str, DataSet] = None

    def __init__(self, name: str, survey: Optional[Survey | BytesIO] = None, contacts: Optional[ContactSet] = None, versions: Optional[Dict[str, DataSet]] = None, log: dict = getLogs()):
        # if log is not None:
        if name in log.keys():
            print("Project exists, loading from log")
            print(json.dumps(log[name], indent=4))
            self.from_dict(log[name])
        else:
            # Project does not exist, create new project
            print("Project does not exist, creating new project")
            self.folder = Folder(name)
            self.name = name
            self.survey = survey
            if contacts is not None:
                self.contact_lists = contacts
            else:
                self.contact_lists = ContactSet([])
            if versions is not None:
                self.versions = versions
            else:
                self.versions = []
            self.sync(log)

    def __str__(self) -> str:
        return self.name

    def __dict__(self) -> dict:
        dict = {
            "name": self.name,
            "driveID": self.folder.driveID,
        }
        if self.instrument is not None:
            dict["instrument"] = self.instrument.to_dict()
        if self.contact_lists is not None:
            dict["contact_lists"] = self.contact_lists.to_dict()
        if self.versions is not None:
            for version in self.versions:
                v = version.to_dict()
                dict[v["name"]] = v
        return dict

    def _make_survey(self, file: BytesIO = None):
        if file is None:
            file = self.instrument
        self.survey = Survey.from_docx(file)

    def to_dict(self) -> dict:
        return self.__dict__()

    # @classmethod
    # def from_dict(cls, dict: dict):
    #     doc = File.from_dict(dict["instrument"])
    #     datasets = []
    #     for data in dict["versions"]:
    #         datasets.append(DataSet.from_dict(data))
    #     contacts = ContactSet.from_dict(dict["contact_lists"])

    #     self = Project(dict["name"], None, contacts, datasets)
    #     self.instrument = doc
    #     return self

    def _upload_instrument(self, file: dict | BytesIO):
        if self.instrument is not None:
            instrument_id = self.instrument.driveID
        else:
            instrument_id = None
        if type(file) == BytesIO:
            print("Uploading instrument")
            self.instrument = File(
                "instrument", driveID=instrument_id, content=file, parent=self.folder.driveID, mimetype="docx")
        elif type(file) == dict:
            print("Uploading instrument from dict")
            file["parent"] = self.folder.driveID
            file["to_replace"] = instrument_id
            self.instrument = File.from_dict(file)

        self._make_survey(self.instrument)

    # pass file along to appropriate method

    def upload_file(self, file: dict | BytesIO):
        if file is None:
            print("No file provided")
            return None
        if type(file) == BytesIO:
            file = File("file", content=file, parent=self.folder.driveID)
        elif type(file) == dict:
            if "SurveyExport" in file["name"] or "response_data" in file["name"] or "All.csv" in file["name"] or "Colnames.csv" in file["name"] or "Xnames.csv" in file["name"]:
                if self.versions is not None and len(self.versions) > 0:
                    self.versions[-1].upload_file(file)
                else:
                    self.new_version()
                    self.versions[-1].upload_file(file)
            elif "CombinedContactList.csv" in file["name"] or "CellPhones.csv" in file["name"] or "LandLines.csv" in file["name"] or re.search("^X_[A-Z0-9]{9}", file["name"]) or re.search("-[a-z0-9]{32}.csv", file["name"]):
                if self.contact_lists is not None:
                    self.contact_lists.upload_file(file)
                else:
                    self.contact_lists = ContactSet(
                        [], parent=self.folder.driveID)
                    self.contact_lists.upload_file(file)
            elif "docx" in file["name"]:
                self._upload_instrument(file)
        self.sync(None)
        return None

    def combine_data(self):
        # TODO: Combine data files into one dataframe
        df = pd.DataFrame()
        lf, df = generateData(self.data, self.contact_lists[0])
        return df

    def to_spss(self):
        # TODO: Combine data files into one dataframe and export to SPSS
        meta = self.survey.to_spss_metadata()
        df = self.combine_data()
        # make sure column names don't have spaces
        df.columns = df.columns.str.replace(" ", "_")
        df.to_csv(self.name+".csv", index=False)
        # export to SPSS using pyreadstat
        pyreadstat.write_sav(df, self.name+".sav", )

    def to_displayr_inputs(self) -> tuple:
        labels, data = generateData(self.data, self.contact_lists[0])
        return data, labels

    def new_version(self):
        # version name will be v01 10.11 etc.
        if self.versions is None:
            self.versions = []
        version = DataSet("v"+str(len(self.versions)+1).zfill(2) +
                          " " + datetime.datetime.now().strftime("%m.%d"), parent=self.folder.driveID)
        self.versions.append(version)

    def from_dict(self, dict: dict):
        self.folder = Folder(dict["name"], dict["driveID"])
        self.name = dict["name"]
        self.versions = []
        if "instrument" in dict.keys():
            self.instrument = File.from_dict(dict["instrument"])
        if "contact_lists" in dict.keys():
            self.contact_lists = ContactSet.from_dict(dict["contact_lists"])
        for key in dict.keys():
            if re.search("^v\d\d", key):
                self.versions.append(DataSet.from_dict(dict[key]))

    def sync(self, log: dict):
        print("Syncing project")
        print(self.to_dict())
        updateLog(self.to_dict(), log) if log is not None else updateLog(
            self.to_dict())

    def get_survey(self) -> Survey:
        if self.survey is None:
            self._make_survey()
        return self.survey


class RegexMatch(str):
    def __eq__(self, pattern: str) -> bool:
        return bool(re.search(pattern, self, flags=re.IGNORECASE))

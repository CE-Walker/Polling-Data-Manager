from __future__ import print_function
from datetime import datetime
import json
import os
from typing import Any, Literal
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload
import gspread
import io


def readSheet(name="https://docs.google.com/spreadsheets/d/1sto8qz1SrVpt4AEWTIqV0YCEPYeUQYiJImugHXpZa78", sheet="2023-24 Sales Tracker"):
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(name)
    worksheet = sh.worksheet(sheet)
    data = worksheet.get_all_values()
    return data


SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
credentials = service_account.Credentials.from_service_account_file(
    'Resources/Credentials.json', scopes=SCOPES)
spreadsheet_service = build('sheets', 'v4', credentials=credentials)
service = build('drive', 'v3', credentials=credentials)

gc = gspread.authorize(credentials)

Polls_Auto = '0AKBlRMpdmXBkUk9PVA'
Archive = '107MbfDHw6wpkWaRWF5gDDzyQLC7dbArS'
Logs = "1yB4a93Jen7g1Dzw_VWR2x07_SJN6Qrji"
ScrubLog = "1eYVUbzn7iOaJgwsgg33b5WRR4NOkBzv6"


def getFolder():
    page_token = None
    while True:
        results = service.files().list(
            pageSize=10, fields="nextPageToken, files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True, corpora='drive', driveId=Polls_Auto, pageToken=page_token).execute()
        years = results.get('files', [])
        if not years:
            print('No files found.')
        found = False
        for year in years:
            if year['name'] == datetime.now().strftime("%Y"):
                return year['id']
        page_token = results.get('nextPageToken', None)
        if page_token is None:
            break
    if not found:
        directory_metadata = {
            'name': datetime.now().strftime("%Y"),
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [Polls_Auto]
        }
        base = service.files().create(body=directory_metadata,
                                      fields='id, name', supportsAllDrives=True).execute()
        return base['id']


Current_Folder = getFolder()


class Folder:
    def __init__(self, name: str, driveID: str = None, parent=Current_Folder):
        self.name = name
        self.parent = parent
        if driveID is None:
            self.driveID = self._createFolder(name, parent)
        else:
            self.driveID = driveID

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.driveID

    def __dict__(self):
        return {
            "name": self.name,
            "driveID": self.driveID,
            "parent": self.parent
        }

    def to_dict(self):
        return self.__dict__()

    @classmethod
    def from_dict(cls, d):
        return Folder(name=d["name"], driveID=d["driveID"], parent=d["parent"])

    def _createFolder(self, name, parent):
        directory_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent]
        }
        base = service.files().create(body=directory_metadata,
                                      fields='id, name', supportsAllDrives=True).execute()
        return base['id']

    def delete(self):
        service.files().delete(
            fileId=self.driveID, supportsAllDrives=True).execute()
        return None

    def update(self, name):
        service.files().update(fileId=self.driveID, body={'name': name},
                               fields='id, name', supportsAllDrives=True).execute()
        self.name = name
        return None

    def get(self):
        return self.driveID

    def get_children(self):
        children = []
        page_token = None
        while True:
            results = service.files().list(
                pageSize=10, fields="nextPageToken, files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True, corpora='drive', driveId=self.driveID, pageToken=page_token).execute()
            files = results.get('files', [])
            if not files:
                print('No files found.')
            for file in files:
                children.append(file)
            page_token = results.get('nextPageToken', None)
            if page_token is None:
                break

        for child in children:
            child["parent"] = self.driveID
            child = File.from_dict(child)
        return children

    def upload_file(self, file: dict | io.BytesIO):
        if type(file) == dict:
            file["parent"] = self.driveID
            file = File.from_dict(file)
        elif type(file) == io.BytesIO:
            file = File(name=file.name, content=file, parent=self.driveID)
        else:
            raise TypeError("file must be either a dict or BytesIO")
        return file


class File:
    def __init__(self, name, driveID=None, content=None, parent=Current_Folder, mimetype: Literal["csv", "sav", "docx", "xlsx"] = None):
        self.name = name
        match mimetype:
            case "csv":
                self.mimetype = "text/csv"
            case "sav":
                self.mimetype = "application/octet-stream"
            case "docx":
                self.mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            case _:
                if name.endswith(".csv"):
                    self.mimetype = "text/csv"
                elif name.endswith(".sav"):
                    self.mimetype = "application/octet-stream"
                elif name.endswith(".docx"):
                    self.mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                self.mimetype = None

        if driveID is None:
            if content is None:
                raise TypeError("Must provide either driveID or content")
            self.driveID = self._createFile(
                name, content, parent, self.mimetype)
        else:
            self.driveID = driveID
        self.content = content
        if content is not None:
            self.update(content)
        self.parent = parent

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        if self.content is None:
            self.content = self._getByID(self.driveID)
        return self.content

    def __dict__(self):
        return {
            "name": self.name,
            "driveID": self.driveID,
            "parent": self.parent
        }

    def to_dict(self):
        return self.__dict__()

    @classmethod
    def from_dict(self, d):
        print(d)
        d["mimetype"] = d["name"].split(".")[-1]
        if "driveID" in d.keys():
            print("driveID")
            return File(name=d["name"], driveID=d["driveID"], content=None, parent=d["parent"], mimetype=d["mimetype"])
        elif "datapath" in d.keys():
            with open(d["datapath"], "rb") as in_file:
                in_file = io.BytesIO(in_file.read())
                replace = d["to_replace"] if "to_replace" in d.keys() else None
                return File(name=d["name"], driveID=replace, content=in_file, parent=d["parent"], mimetype=d["mimetype"])
        else:
            return NotImplementedError

    @classmethod
    def _createFile(cls, name, content, parent, mimetype="text/csv"):
        media = MediaIoBaseUpload(
            content, mimetype=mimetype)
        file = service.files().create(body={'name': name, 'parents': [parent]},
                                      fields='id, name', media_body=media, supportsAllDrives=True).execute()
        return file['id']

    @classmethod
    def _getByID(cls, driveID):
        file = service.files().get_media(
            fileId=driveID, supportsAllDrives=True)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, file)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        file = fh.getvalue()
        return io.BytesIO(file)

    def _updateByID(self, driveID, content, mimetype="text/csv"):
        media = MediaIoBaseUpload(
            content, mimetype=mimetype)
        service.files().update(fileId=driveID, body={'name': self.name},
                               fields='id, name', supportsAllDrives=True, media_body=media).execute()
        return None

    def delete(self):
        service.files().delete(
            fileId=self.driveID, supportsAllDrives=True).execute()
        return None

    def update(self, content):
        self._updateByID(self.driveID, content, self.mimetype)
        self.content = content
        return None

    def get(self):
        self.content = self._getByID(self.driveID)
        return self.content

    def __dict__(self):
        return {
            "name": self.name,
            "driveID": self.driveID,
            "parent": self.parent
        }


def init_project(name, logs) -> dict:
    directory_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [Current_Folder]
    }
    base = service.files().create(body=directory_metadata,
                                  fields='id, name', supportsAllDrives=True).execute()
    cl = service.files().create(body={'name': 'Contact Lists', 'mimeType': 'application/vnd.google-apps.folder',
                                      'parents': [base['id']]}, fields='id, name', supportsAllDrives=True).execute()
    project_log = {
        'name': name,
        'folder': base['id'],
        'contact_lists': {
            'folder': cl['id'],
        },
        'versions': {

        },
        'instrument': '',
    }
    logs[name] = project_log
    updateLog(project_log, logs)
    return project_log


def checkProject(name) -> dict:
    # Download log.json from Polls_Auto shared drive
    # Hardcode log id for speed so we don't have to scan the whole folder
    # Drive API scans from newest to oldest so this will always be last
    # because it is updated every time a new poll is created it will grow to be very large
    # so we will need to archive it every so often
    file = service.files().get_media(
        fileId=Logs, supportsAllDrives=True)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, file)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    logs = fh.getvalue().decode('utf-8')
    logs = json.loads(logs)
    if name in logs.keys():
        print("found existing project")
        return logs[name]
    else:
        print("creating new project")
        print(name)
        return init_project(name, logs)


def archiveLog():
    # Download log.json from Polls_Auto shared drive
    # Copy contents to date stamped file in Polls_Auto/Archive
    # Remove contents from log.json but make sure not to delete the file
    # so that we can continue to use it with it's hardcoded id
    log = getLogs()

    # set contents of archive log to current log
    archive_log = log

    # set current log to empty
    log = {}

    # create dated log in archive folder
    date = datetime.now().strftime("%Y-%m-%d")

    with open(date+'-log.json', 'w') as outfile:
        json.dump(archive_log, outfile)

    media = MediaFileUpload(
        date+'-log.json')

    file_metadata = {
        'name': date+'-log.json',
        'parents': [Archive]
    }

    file = service.files().create(body=file_metadata, media_body=media,
                                  fields='id, name', supportsAllDrives=True).execute()
    os.remove(date+'-log.json')

    # update log.json
    with open('log.json', 'w') as outfile:
        json.dump(log, outfile)

    media = MediaFileUpload(
        'log.json')

    file_metadata = {
        'name': 'log.json',
    }

    file = service.files().update(fileId=Logs, body=file_metadata,
                                  fields='id, name', supportsAllDrives=True, media_body=media).execute()

    # delete local log.json
    os.remove('log.json')
    return log


def getLogs() -> dict:
    # Download log.json from Polls_Auto shared drive
    # Hardcode log id for speed so we don't have to scan the whole folder
    # Drive API scans from newest to oldest so this will always be last
    # because it is updated every time a new poll is created it will grow to be very large
    # so we will need to archive it every so often
    file = service.files().get_media(
        fileId=Logs, supportsAllDrives=True)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, file)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    logs = fh.getvalue().decode('utf-8')
    logs = json.loads(logs)
    return logs


def updateLog(update, logs=getLogs()):
    logs[update["name"]] = update
    print("updating project " + update["name"])

    logs_bytes = json.dumps(logs).encode('utf-8')
    media = MediaIoBaseUpload(io.BytesIO(logs_bytes), mimetype='text/json')

    file_metadata = {
        'name': 'log.json'
    }

    file = service.files().update(fileId=Logs, body=file_metadata,
                                  fields='id, name', supportsAllDrives=True, media_body=media).execute()


def getDriveFile(log, file_type):
    if log.keys().__contains__(file_type) and log[file_type] != "":
        file = service.files().get_media(
            fileId=log[file_type], supportsAllDrives=True)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, file)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        file = fh.getvalue()
    elif log["versions"].keys().__contains__(file_type):
        file = service.files().get_media(
            fileId=log["versions"][file_type]["folder"], supportsAllDrives=True)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, file)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        file = fh.getvalue()
    elif log["contact_lists"].keys().__contains__(file_type):
        file = service.files().get_media(
            fileId=log["contact_lists"][file_type], supportsAllDrives=True)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, file)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        file = fh.getvalue()
    else:
        print("File not found")
        file = None
    return file


def newVersionFolder(log):
    versions = log["versions"]
    version_number = "V"+str(len(versions.keys())+1).zfill(2) + \
        " "+datetime.now().strftime("%m.%d")

    version = service.files().create(body={'name': version_number, 'mimeType': 'application/vnd.google-apps.folder',
                                           'parents': [log['folder']]}, fields='id, name', supportsAllDrives=True).execute()
    supporting_documents = service.files().create(body={'name': "Supporting Documents", 'mimeType': 'application/vnd.google-apps.folder',
                                                        'parents': [version['id']]}, fields='id, name', supportsAllDrives=True).execute()
    input_files = service.files().create(body={'name': "Input Files", 'mimeType': 'application/vnd.google-apps.folder',
                                               'parents': [version['id']]}, fields='id, name', supportsAllDrives=True).execute()

    log["versions"][version_number] = {
        "folder": version['id'],
        "supporting_documents": {
            "folder": supporting_documents['id'],
            "weights": "",
            "output_data": "",
            "column_names": "",
            "xnames": "",

        },
        "input_files": {
            "folder": input_files['id'],
            "alchemer_output": "",
            "broadnet_output": "",
            "live_call_output": "",
        },
    }

    updateLog(log)
    return version_number


def checkVersion(log):
    version_number = 0
    for version in log["versions"].keys():
        # return highest version number
        if int(version[1:3]) > version_number:
            print("found existing version")
            version_number = int(version[1:3])
            name = version
    if version_number == 0:
        print("creating new version")
        return newVersionFolder(log)
    else:
        return name


def uploadDrive(log, file, file_type, version=""):
    folder = log
    mime_type = "text/csv"
    check = file_type
    match file_type:
        case "raw_data":
            check = file['name']
            if file['name'].endswith(".csv"):
                folder = log['contact_lists']
            else:
                print(file['name'])
                return TypeError("File must be a .csv")
        case "instrument":
            if file['name'].endswith(".docx"):
                folder = log
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                return TypeError("File must be a .docx")
        case "combined_list":
            if file['name'].endswith(".csv"):
                folder = log['contact_lists']
            else:
                return TypeError("File must be a .csv")
        case "cell_list":
            if file['name'].endswith(".csv"):
                folder = log['contact_lists']
            else:
                return TypeError("File must be a .csv")
        case "landline_list":
            if file['name'].endswith(".csv"):
                folder = log['contact_lists']
            else:
                return TypeError("File must be a .csv")
        case "weights":
            folder = log['supporting_documents']
        case "alchemer_output":
            if file['name'].endswith(".csv"):
                folder = log["versions"][version]["input_files"]
            else:
                return TypeError("File must be a .csv")
        case "broadnet_output":
            if file['name'].endswith(".csv"):
                folder = log["versions"][version]["input_files"]
            else:
                return TypeError("File must be a .csv")
        case "output_data":
            folder = log["versions"][version]["supporting_documents"]
        case "column_names":
            folder = log["versions"][version]["supporting_documents"]
        case "xnames":
            folder = log["versions"][version]["supporting_documents"]
        case _:
            folder = log

    if check in folder.keys() and folder[check] != "":
        print("Updating "+file_type)
        media = MediaFileUpload(
            file['datapath'], mimetype=mime_type)
        service.files().update(fileId=folder[file_type if file_type != 'raw_data' else file['name']], body={'name': file['name']},
                               fields='id, name', supportsAllDrives=True, media_body=media).execute()

        updateLog(log)
    else:
        print("Uploading "+file_type)
        media = MediaFileUpload(
            file['datapath'], mimetype=mime_type)
        file = service.files().create(body={'name': file['name'], 'parents': [folder['folder']]},
                                      fields='id, name', supportsAllDrives=True, media_body=media).execute()
        folder[file_type] = file['id']
        match file_type:
            case "raw_data":
                log['contact_lists'][file['name']] = file['id']
            case "instrument":
                log[file_type] = file['id']
            case "combined_list":
                log['contact_lists'][file_type] = file['id']
            case "cell_list":
                log['contact_lists'][file_type] = file['id']
            case "landline_list":
                log['contact_lists'][file_type] = file['id']
            case "weights":
                log['version'][version]['supporting_documents'][file_type] = file['id']
            case "alchemer_output":
                log["versions"][version]["input_files"][file_type] = file['id']
            case "broadnet_output":
                log["versions"][version]["input_files"][file_type] = file['id']
            case "output_data":
                log["versions"][version]["supporting_documents"][file_type] = file['id']
            case "column_names":
                log["versions"][version]["supporting_documents"][file_type] = file['id']
            case "xnames":
                log["versions"][version]["supporting_documents"][file_type] = file['id']
            case _:
                log[file_type] = file['id']

        updateLog(log)

    #     if file_type == "raw_data" or file_type == "combined_list" or file_type == "cell_list" or file_type == "landline_list":
    #         folder = log['contact_lists']["folder"]
    #         found = False
    #         for key in log["contact_lists"].keys():
    #             if key == file['name']:
    #                 found = True
    #                 print("Updating "+file_type)
    #                 media = MediaFileUpload(
    #                     file['datapath'], mimetype='text/csv')
    #                 service.files().update(fileId=log["contact_lists"][key], body={'name': file['name']},
    #                                        fields='id, name', supportsAllDrives=True, media_body=media).execute()
    #                 return file
    #         if not found:
    #             print("Uploading "+file_type)
    #             media = MediaFileUpload(
    #                 file['datapath'], mimetype='text/csv')
    #             file = service.files().create(body={'name': file['name'], 'parents': [folder]},
    #                                           fields='id, name', supportsAllDrives=True, media_body=media).execute()
    #             if not log.keys().__contains__(file_type):
    #                 log[file_type] = {}
    #             log["contact_lists"][file['name']] = file['id']

    #     elif file_type == "broadnet_output" or file_type == "alchemer_output":
    #         if log["versions"][version]["input_files"][file_type] != "":
    #             print("Updating "+file_type)
    #             media = MediaFileUpload(
    #                 file['datapath'], mimetype='text/csv')
    #             file = service.files().update(body={'name': file['name'], 'parents': [folder]},
    #                                           fields='id, name', supportsAllDrives=True, media_body=media).execute()
    #             log["versions"][version]["input_files"][file_type] = file['id']
    #         else:
    #             print("Uploading "+file_type)
    #             media = MediaFileUpload(
    #                 file['datapath'], mimetype='text/csv')
    #             file = service.files().create(body={'name': file['name'], 'parents': [folder]},
    #                                           fields='id, name', supportsAllDrives=True, media_body=media).execute()
    #             log["versions"][version]["input_files"][file_type] = file['id']
    #     elif file_type == "output_data" or file_type == "column_names" or file_type == "xnames":
    #         if log["versions"][version]["supporting_documents"][file_type] != "":
    #             print("Updating "+file_type)
    #             media = MediaFileUpload(
    #                 file['datapath'], mimetype='text/csv')
    #             file = service.files().update(body={'name': file['name'], 'parents': [folder]},
    #                                           fields='id, name', supportsAllDrives=True, media_body=media).execute()
    #             log["versions"][version]["supporting_documents"][file_type] = file['id']
    #         else:
    #             print("Uploading "+file_type)
    #             media = MediaFileUpload(
    #                 file['datapath'], mimetype='text/csv')
    #             file = service.files().create(body={'name': file['name'], 'parents': [folder]},
    #                                           fields='id, name', supportsAllDrives=True, media_body=media).execute()
    #             log["versions"][version]["supporting_documents"][file_type] = file['id']
    #     else:
    #         print("Updating "+file_type)
    #         if file_type == "instrument":
    #             media = MediaFileUpload(
    #                 file['datapath'], mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    #         else:
    #             media = MediaFileUpload(
    #                 file['datapath'], mimetype='text/csv')
    #         service.files().update(fileId=log[file_type], body={'name': file['name']},
    #                                fields='id, name', supportsAllDrives=True, media_body=media).execute()
    # else:
    #     file_metadata = {
    #         'name': file['name'],
    #         'parents': [folder]
    #     }
    #     if file_type == "instrument":
    #         media = MediaFileUpload(
    #             file['datapath'], mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    #     else:
    #         media = MediaFileUpload(
    #             file['datapath'], mimetype='text/csv')
    #     file = service.files().create(body=file_metadata, media_body=media,
    #                                   fields='id, name', supportsAllDrives=True).execute()

    updateLog(log)
    return file


def getByID(file_id):
    file = service.files().get_media(
        fileId=file_id, supportsAllDrives=True)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, file)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    file = fh.getvalue()
    return file


def updateByID(file_id, file):
    media = MediaFileUpload(
        file)
    service.files().update(fileId=file_id, body={'name': file['name']},
                           fields='id, name', supportsAllDrives=True, media_body=media).execute()
    return None


def deleteByID(file_id):
    service.files().delete(
        fileId=file_id, supportsAllDrives=True).execute()
    return None


def deleteFile(log, file_type, version=""):
    if log.keys().__contains__(file_type) and log[file_type] != "":
        log[file_type] = ""
        updateLog(log)
        service.files().delete(
            fileId=log[file_type], supportsAllDrives=True).execute()
    elif log["versions"].keys().__contains__(file_type):
        log["versions"][file_type] = ""
        updateLog(log)
        service.files().delete(
            fileId=log["versions"][version][file_type], supportsAllDrives=True).execute()
    elif log["contact_lists"].keys().__contains__(file_type):
        file = log["contact_lists"][file_type]
        log["contact_lists"].pop(file_type)
        updateLog(log)
        service.files().delete(
            fileId=log["contact_lists"][file], supportsAllDrives=True).execute()

    return None

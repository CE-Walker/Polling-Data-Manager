
# word doc library
from io import BytesIO
from pathlib import Path
import re
import requests
import urllib


host_name = 'https://app.displayr.com'

uploaded_file_dictionary = {}
uploaded_data_files = []


def UploadFile(file_path):
    url = "%s/API/Upload" % host_name
    response = requests.post(url, files={'file': open(file_path, 'rb')})
    upload_id = response.headers['UploadID']
    uploaded_file_dictionary[file_path] = upload_id
    print("File %s uploaded" % file_path)
    return upload_id


def UploadRawFile(file_raw: BytesIO, file_name):
    print(file_raw)
    print(file_raw.getvalue())
    url = "%s/API/Upload" % host_name
    response = requests.post(url, files={'file': file_raw})
    print(response.headers)
    upload_id = response.headers['UploadID']
    uploaded_file_dictionary[file_name] = upload_id
    print("File %s uploaded" % file_name)
    return upload_id


def UploadData(replace, file_path):
    upload_id = UploadFile(file_path)
    uploaded_data_files.append(
        {'upload_id': upload_id, 'path': file_path, 'replace': replace})


def UploadRawData(replace, file_raw, file_name):
    print(file_raw)
    upload_id = UploadRawFile(file_raw, file_name)
    uploaded_data_files.append(
        {'upload_id': upload_id, 'path': file_name, 'replace': replace})


# The following can be found in the company settings page if you are logged
# into displayr.com as a site admin.
company_secret = '4a80bd88-505e-4289-a4d8-a9fe5757e5c9'

# Contact name for new project
new_project_contact_name = 'Demo'

# Names of Template Files
template_data = 'TemplateData_Flex.csv'
template_colnames = 'TemplateData_RepublicanPrimary_ColNames.csv'
template_xnames = 'TemplateData_Flex_Xnames.csv'


def UploadQPack(qpack_file_path='../Resources/API_Template.QPack', new_project_name='demo'):
    print('Creating project...')
    url = "%s/API/NewProjectFromQPack?file_name=%s&company=%s&name=%s&upload_id=%s&public_url=false&contact=Fred" % (
        host_name, qpack_file_path,  company_secret, new_project_name, uploaded_file_dictionary[qpack_file_path])
    print(url)
    response = requests.post(url)
    print("\n"*3)
    print(response)
    print("\n"*3)
    if 'ProjectSecret' in response.headers:
        project_secret = response.headers['ProjectSecret']
        print("Project '%s' created, with project secret: %s" %
              (new_project_name, project_secret))
    else:
        if ('Success' in str(response.content)):
            print("Success")
        else:
            print(re.search(
                '<b>(.*)</b>', str(response.content), re.IGNORECASE).group(1)
            )
        exit()

    return project_secret


def updateData(project_secret):
    print('Updating data...')
    for file_info in uploaded_data_files:
        params = {'project': project_secret, 'data_name': file_info['replace'], 'new_data_file_name': file_info[
            'path'], 'upload_id': file_info['upload_id'], 'new_serial': 1, 'abort': 'Never'}
        url = "%s/API/ImportUpdatedData?%s" % (host_name,
                                               urllib.parse.urlencode(params))
        response = requests.post(url)
        if response.status_code != 200:
            print("Problem using data file %s" % file_info['path'])
        # file = open(file_info['path']+".html",
        #             'w')
        # file.write(str(response.content).replace('\\r\\n', ''))
        # file.close()
        print("Data file %s updated" % file_info['path'])


def runScript(secret, script):
    print('Running script...')
    url = "%s/API/RunScript?project=%s&abort=OnWarning" % (
        host_name, secret)
    response = requests.post(url, data=script)
    if response.status_code != 200:
        print("Problem running script")
    if ('Success' in str(response.content)):
        print("Success")
    else:
        print(re.search(
            '<b>(.*)</b>', str(response.content), re.IGNORECASE).group(1)
        )


def dataRefresh(log, data, colnames, xnames):
    name = log['project_name']
    project_secret = log['secret']
    UploadRawData(template_data, data, name+"_All.csv")
    UploadRawData(template_colnames,
                  colnames, name+"_ColNames.csv")
    UploadRawData(template_xnames, xnames, name+"_Xnames.csv")

    updateData(project_secret)

    with open('Resources/tidy.QScript', 'r') as file:
        qscript = file.read()
        # append functions to qscript
        qscript += "methodology_page();"
        runScript(project_secret, qscript)
    response = requests.post(
        "%s/API/PublishProject?project=%s&view_mode_access=L" % (host_name, project_secret), data=qscript)
    if response.status_code != 200:
        print("Problem publishing project")
        return "Problem publishing project"
    if ('Success' in str(response.content)):
        print(response.content)
        print(response.headers["ProjectUrl"])
        # iframe =
        return response.headers["ProjectUrl"]


def initializeDeck(input, data: BytesIO, colnames, xnames=None, branding="Standard"):
    new_project_name = input
    qpack_file_path = Path("Resources/API_Template-" +
                           branding+".QPack").resolve()
    print(qpack_file_path)

    UploadFile(qpack_file_path)
    print(data)

    project_secret = UploadQPack(qpack_file_path, new_project_name)

    UploadRawData(template_data, data, "TemplateData_Flex.csv")
    UploadRawData(template_colnames,
                  colnames, "TemplateData_RepublicanPrimary_ColNames.csv")
    # UploadRawData(template_xnames, xnames, "TemplateData_Flex_Xnames.csv")

    updateData(project_secret)

    with open('Resources/tidy.QScript', 'r') as file:
        qscript = file.read()
        # append functions to qscript
        qscript += "top_lines_to_pages();"
        qscript += "questions_to_pages(questions);"
        runScript(project_secret, qscript)
    response = requests.post(
        "%s/API/PublishProject?project=%s&view_mode_access=L" % (host_name, project_secret), data=qscript)
    if response.status_code != 200:
        print("Problem publishing project")
        return "Problem publishing project"
    if ('Success' in str(response.content)):
        print(response.content)
        print(response.headers["ProjectUrl"])
        # iframe =
        return response.headers["ProjectUrl"], project_secret


def deleteDeck(secret):
    response = requests.post(
        "%s/API/DeleteProject?project=%s" % (host_name, secret))
    if response.status_code != 200:
        print("Problem deleting project")
        return "Problem deleting project"
    if ('Success' in str(response.content)):
        print(response.content)
        return response.content

from io import BytesIO
from typing import List
import pandas as pd
import re


def l2_match(x):
    match x:
        case "Voters_Age":
            return "Age"
        case "Voters_Gender":
            return "Gender"
        case "EthnicGroups_EthnicGroup1Desc":
            return "Race"
        case "Parties_Description":
            return "Party"
        case "F":
            return "Female"
        case "M":
            return "Male"
        case "East and South Asian":
            return "Asian"
        case "European":
            return "White"
        case "Hispanic and Portuguese":
            return "Hispanic"
        case "Likely African-American":
            return "Black"
        case "Democratic":
            return "Democrat"
        case "Highschool":
            return "HS"
        case "65-100":
            return "65+"
        case _: return x


def compare(weight, response):
    weights = pd.read_csv(weight, header=None)
    weights.columns = ["Category", "Field", "Count"]
    responses = pd.read_csv(response)

    weights["Category"] = weights["Category"].transform(lambda x: l2_match(x))
    weights["Field"] = weights["Field"].transform(lambda x: l2_match(x))
    weights["Count"] = weights["Count"].transform(
        lambda x: int(re.sub(",", "", x)))
    weights["Percentage"] = weights["Count"].transform(
        lambda x: round((x/weights["Count"][0])*100, 2))

    weights["Response Make Up"] = 0

    weights["Response Make Up"]
    for i in weights["Category"].unique():
        if i == "Total":
            weights.loc[(weights["Category"] == i) & (
                weights["Field"] == "Total"), "Response Make Up"] = responses["Age"].count()
        if i in responses.columns:
            for j in weights["Field"].unique():
                if j in responses[i].unique():
                    weights.loc[(weights["Category"] == i) & (
                        weights["Field"] == j), "Response Make Up"] = responses[i].groupby(responses[i]).count()[j]

    # remove rows with 0 response make up
    weights = weights[weights["Response Make Up"] != 0]
    weights["Percent Make Up"] = weights["Response Make Up"].transform(
        lambda x: round((x/weights["Response Make Up"][0])*100, 2))

    weights["Difference"] = weights["Percent Make Up"] - weights["Percentage"]

    weights["Difference"] = weights["Difference"].transform(
        lambda x: round(x, 2))

    return weights


def generateData(data: List[BytesIO], contactlist: BytesIO):
    alchemer = pd.read_csv(data[0])
    broadnet = pd.read_csv(data[1])
    contactlist = pd.read_csv(contactlist)
    anti_column = ["Response ID", "Time Started", "Status",
                   "Contact ID", "Legacy Comments", "Comments", "Language",
                   "Referer", "SessionID", "User Agent", "Tags",
                   "IP Address", "Longitude", "Latitude",
                   "Country", "City", "State/Region", "Postal", "Timestamp"]

    for column in anti_column:
        if alchemer.columns.__contains__(column):
            alchemer.drop(column, axis=1, inplace=True)

    # rename Completion Code to ID
    alchemer.rename(columns={"Completion Code": "ID"}, inplace=True)

    b_columns = [
        "calltime", "ID"
    ]
    for column in broadnet.columns:
        if column not in b_columns:
            if re.search("\d+:MC:_response:", column):
                label = re.sub("\d+:MC:_response:", "", column)
                broadnet.drop(column, axis=1, inplace=True)
            elif re.search("\d+:MC:_text", column):
                broadnet.rename(columns={column: label}, inplace=True)
            else:
                broadnet.drop(column, axis=1, inplace=True)

    alchemer["Date Submitted"] = pd.to_datetime(
        alchemer["Date Submitted"]).dt.strftime("%m/%d/%Y")
    broadnet["calltime"] = pd.to_datetime(
        broadnet["calltime"]).dt.strftime("%m/%d/%Y")

    labels = pd.DataFrame()
    labels["Labels"] = broadnet.columns
    labels["Full"] = alchemer.columns

    data = pd.DataFrame({"Date Submitted": pd.concat([alchemer["Date Submitted"], broadnet["calltime"]], ignore_index=True),
                         "ID": pd.concat([alchemer["ID"], broadnet["ID"]], ignore_index=True)
                         })
    num = 0
    for column in alchemer.columns:
        if column not in ["Date Submitted", "ID"]:
            if re.search("(which|what) party do you most align with", column.lower()):
                alchemer.rename(columns={column: "Party"}, inplace=True)
            elif re.search("what is your age", column.lower()):
                alchemer.rename(columns={column: "Age"}, inplace=True)
            elif re.search("(what|which) ideology is most in line with your views", column.lower()):
                alchemer.rename(columns={column: "Ideology"}, inplace=True)
            elif re.search("are you male or female", column.lower()):
                alchemer.rename(columns={column: "Gender"}, inplace=True)
            elif re.search("what is your race", column.lower()):
                alchemer.rename(columns={column: "Race"}, inplace=True)
            elif re.search("what is the highest level of education you have (completed|attained) so far", column.lower()):
                alchemer.rename(columns={column: "Education"}, inplace=True)
            else:
                num += 1
                alchemer.rename(columns={column: "Q"+str(num)}, inplace=True)

    num = 0
    for column in broadnet.columns:
        if column == "calltime":
            broadnet.rename(columns={column: "Date Submitted"}, inplace=True)
        if column not in ["calltime", "ID", "Race", "Gender", "Age", "Party", "Education", "Ideology"]:
            num += 1
            broadnet.rename(columns={column: "Q"+str(num)}, inplace=True)

    print(alchemer.columns)
    print(broadnet.columns)

    for column in broadnet.columns:
        if column not in ["Date Submitted", "ID"]:

            data[column] = pd.concat(
                [alchemer[column], broadnet[column]], ignore_index=True)
            match column:
                case "Race":
                    data[column] = data[column].transform(
                        lambda x: re.sub("african american", "Black", str(x), flags=re.IGNORECASE))
                case "Ideology":
                    data[column] = data[column].transform(
                        lambda x: re.sub("conservative", "Conserv.", str(x), flags=re.IGNORECASE))
                case "Education":
                    data[column] = data[column].transform(
                        lambda x: re.sub("high school|hs|some college", "HS", str(x), flags=re.IGNORECASE))
                    data[column] = data[column].transform(
                        lambda x: re.sub("college graduate", "College", str(x), flags=re.IGNORECASE))
                    data[column] = data[column].transform(lambda x: re.sub(
                        "grad(|uate) degree or higher", "Grad+", str(x), flags=re.IGNORECASE))
                case "Age":
                    data[column] = data[column].transform(
                        lambda x: re.sub("65 or older", "65+", str(x), flags=re.IGNORECASE))
                case "Party":
                    data[column] = data[column].transform(
                        lambda x: re.sub(".+?[^(republican|democrat|independent|other)].+?", "Other", str(x), flags=re.IGNORECASE))
                    data[column] = data[column].transform(
                        lambda x: re.sub("democrat", "Dem.", str(x), flags=re.IGNORECASE))
                    data[column] = data[column].transform(
                        lambda x: re.sub("republican", "Rep.", str(x), flags=re.IGNORECASE))
                    data[column] = data[column].transform(
                        lambda x: re.sub("independent", "Ind.", str(x), flags=re.IGNORECASE))

    labels["Generic"] = data.columns

    q_count = 0
    for column in contactlist.columns:
        if "Q" not in column:
            q_count += 1

    # create a summary table explaining the drop off of each question
    # summary = pd.DataFrame()
    # summary["Question"] = contactlist.columns[labels["Generic"]]
    # summary["Total"] = contactlist[summary["Question"]].count()
    # summary["Percentage"] = summary["Total"].transform(
    #     lambda x: x/summary["Total"][0])
    # summary["Percentage"] = summary["Percentage"].transform(
    #     lambda x: round(x*100, 2))

    # append columns from combined contact list to data
    for column in contactlist.columns:
        if "Append" in column:
            data[column] = contactlist[column]

    return labels, data


# with open("./22801_230935_va_hd_97_brushfire_poll_9_18_response_data.csv", "rb") as file:
#     brdnt = BytesIO(file.read())

# with open("./20230920141020-SurveyExport.csv", "rb") as file:
#     alch = BytesIO(file.read())

# with open("./230935_VA HD 97 Brushfire Poll_9.18.23_CombinedContactList.csv", "rb") as file:
#     cl = BytesIO(file.read())

# labels, data = generateData(alch, brdnt, cl)
# labels.to_csv("labels.csv", index=False)
# data.to_csv("data.csv", index=False)

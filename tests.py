import pandas as pd
from modules.survey import Project

pname = "221077_VA GOP Delegate Poll 1.5"
p = Project(pname)

file = {
    "name": "CellPhones.csv",
    "datapath": "./Resources/CellPhones-Example.csv",
}

p.upload_file(file)


print(p.get_survey())

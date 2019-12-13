import boto3
import re
import json
import glob
from botocore.exceptions import ClientError
from collections import OrderedDict


class SSMClient:
    def __init__(self, output_path="Output/*.json"):
        self.ssm_client = boto3.client('ssm')
        self.output_path = output_path

    def check_ssm_documents(self):
        automation_documents = glob.glob(self.output_path)

        if automation_documents:
            for automation_document in automation_documents:
                print(automation_document)
                match_file_name = re.match(r"Output\/(.*)\.json", automation_document)
                automation_document_name = match_file_name.group(1)

                try:
                    response = self.ssm_client.get_document(
                        Name=automation_document_name,
                        DocumentVersion='$LATEST',
                    )

                    # automation document exists, check whether it needs to be updated
                    document_content = json.loads(response['Content'])

                    with open(automation_document) as automation_doc:
                        automation_doc_json = json.load(automation_doc)

                    if automation_doc_json != document_content:
                        self.update_ssm_document(automation_document_name, automation_doc_json)

                except ClientError as e:
                    if e.response['Error']['Code'] == 'InvalidDocument':
                        # automation document does not exist, create the document
                        self.create_ssm_document(automation_document)

    def create_ssm_document(self, automation_document):
        print("create_ssm_document:")
        with open(automation_document) as automation_doc:
            automation_doc_json = json.load(automation_doc)

        match_file_name = re.match(r"Output\/(.*)\.json", automation_document)
        automation_document_name = match_file_name.group(1)

        response = self.ssm_client.create_document(
            Content=json.dumps(automation_doc_json),
            Name=automation_document_name,
            DocumentType='Automation',
            DocumentFormat='JSON',
        )

        print(response)

    def update_ssm_document(self, document_name, document_content):
        print("update_ssm_document:")
        print("update_ssm_document: updating {}".format(document_name))
        response = self.ssm_client.update_document(
            Content=json.dumps(document_content),
            Name=document_name,
            DocumentVersion='$LATEST',
            DocumentFormat='JSON'
        )

        update_response = self.ssm_client.update_document_default_version(
            Name=document_name,
            DocumentVersion=response["DocumentDescription"]["DocumentVersion"]
        )['ResponseMetadata']['HTTPStatusCode']

        if update_response == 200:
            print("update_ssm_document: updating {} was successful".format(document_name))
        else:
            print("update_ssm_document: failed to update {}, http response {}".format(document_name, update_response))

    def update_ssm_sharing_permissions(self, document_permissions_config):
        print("update_ssm_sharing_permissions:")
        for document in document_permissions_config:
            document_name = document['name']
            document_permissions = ['{}'.format(x) for x in document['awsAccounts']]

            currently_shared_accounts = self.ssm_client.describe_document_permission(
                Name=document_name,
                PermissionType='Share'
            )['AccountIds']

            share_document = [x for x in document_permissions if x not in currently_shared_accounts]
            unshare_document = [x for x in currently_shared_accounts if x not in document_permissions]

            if share_document or unshare_document:
                if share_document:
                    print("update_ssm_sharing_permissions: sharing {} to {}".format(document_name, share_document))

                if unshare_document:
                    print("update_ssm_sharing_permissions: unsharing {} from {}".format(document_name, unshare_document))

                response = self.ssm_client.modify_document_permission(
                    Name=document_name,
                    PermissionType='Share',
                    AccountIdsToAdd=share_document,
                    AccountIdsToRemove=unshare_document
                )['ResponseMetadata']['HTTPStatusCode']

                if response == 200:
                    print("update_ssm_sharing_permissions: {} permissions updated successfully".format(document_name))
                else:
                    print("update_ssm_sharing_permissions: {} permissions failed to update, error code:".format(
                        document_name,
                        response)
                    )
            else:
                print("update_ssm_sharing_permissions: {} has no changes, skipping.".format(document_name))

    @staticmethod
    def convert_document_to_dot_graph(doc_filename):
        # Loading the document as json
        # with open(doc_filename, 'r') as jsonfile:
        #     json_doc = json.load(jsonfile, object_pairs_hook=OrderedDict)

        json_doc = doc_filename
        # Initializating the graph variable with the document description and the default Start and End nodes
        graph = []
        graph.append("// {}".format(json_doc["description"]))
        graph.append("digraph {")
        graph.append("    Start [label=Start]")
        graph.append("    End [label=End]")

        # If the document step does not explicitly define the next step on failure and on success,
        # then the next step from the document will use the following variables to create the edge
        add_edge_from_previous_step = False
        label = ""
        previous_step_name = ""

        for index, step in enumerate(json_doc["mainSteps"]):
            if add_edge_from_previous_step:
                graph.append("    {} -> {} [label={}]".format(
                    previous_step_name, step["name"], label))
                add_edge_from_previous_step = False

            # Create the edge from the Start node if this is the first node of the document
            if index == 0:
                graph.append("    {} -> {}".format("Start", step["name"]))

            # If action is aws:branch, checking all choices to visualize each branch
            if step["action"].lower()  == "aws:branch":
                for choice in step["inputs"]["Choices"]:
                    next_step = choice["NextStep"]
                    del choice["NextStep"]
                    # Removing first and last character from the choice (that removes the curly brackets),
                    # escaping and adding a new line for each comma)
                    label = "\"{}\"".format(json.dumps(
                        choice)[1:-1].replace('", "', '"\\l"').replace('"', '\\"'))
                    graph.append("    {} -> {} [label={}]".format(
                        step["name"], next_step, label))

                if "Default" in step["inputs"]:
                    graph.append("    {} -> {} [label={}]".format(
                        step["name"], step["inputs"]["Default"], "Default"))
            else:
                # If nextStep is used in the step, using it to create the edge,
                # else we save the current step information to be able to create the edge when inspecting the next available step
                if "nextStep" in step:
                    graph.append("    {} -> {} [label={}]".format(
                        step["name"], step["nextStep"], "onSuccess"))
                # When isEnd is true, create an edge to the End node
                elif "isEnd" in step:
                    if "{}".format(step["isEnd"]).lower() == "true" or step["isEnd"] is True:
                        graph.append(
                            "    {} -> {} [label={}]".format(step["name"], "End", "onSuccess"))
                else:
                    add_edge_from_previous_step = True
                    label = "onSuccess"
                    previous_step_name = step["name"]

            # If onFailure is Abort or not specified, create an edge to the End node.
            if "onFailure" in step:
                if step["onFailure"].lower() == "abort":
                    graph.append("    {} -> {} [label={} color=\"red\"]".format(
                        step["name"], "End", "onFailure"))
                # If onFailure is Continue, we look for nextStep,
                # or save the current step information to be able to create the edge when inspecting the next available step
                elif step["onFailure"].lower()  == "continue":
                    if "nextStep" in step:
                        label = "onFailure color=\"red\""
                        if "isCritical" in step:
                            if "{}".format(step["isCritical"]).lower() == "false" or step["isCritical"] is False:
                                label = "onFailure"
                        graph.append("    {} -> {} [label={}]".format(
                            step["name"], step["nextStep"], label))
                    else:
                        add_edge_from_previous_step = True
                        label = "onFailure color=\"red\""
                        previous_step_name = step["name"]
                # Lastly, retrieve the next step from onFailure directly
                else:
                    label = "onFailure color=\"red\""
                    if "isCritical" in step:
                        if "{}".format(step["isCritical"]).lower() == "false" or step["isCritical"] is False:
                            label = "onFailure"
                    graph.append("    {} -> {} [label={}]".format(
                        step["name"], step["onFailure"].replace("step:", ""), label))
            else:
                graph.append("    {} -> {} [label={}]".format(
                    step["name"], "End", "onFailure color=\"red\""))

        graph.append("}")

        return "\n".join(graph)

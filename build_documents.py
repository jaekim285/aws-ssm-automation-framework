import json
import ssm_client
import logging
import os
import boto3
import yaml
from botocore.exceptions import ClientError

BUILD_CONFIG = "build_documents_config.json"
PERMISSIONS_CONFIG = "document_permissions.json"
LOGGER = logging.getLogger(__name__)
OUTPUT_PATH = "Output"
s3_client = boto3.client('s3')


def aws_tag_multi_constructor(loader, tag_suffix, node):
    if tag_suffix not in ['Ref', 'Condition']:
        tag_suffix = "Fn::{}".format(tag_suffix)

    if tag_suffix == "Fn::GetAtt":
        result = node.value.split(".")
    elif isinstance(node, yaml.ScalarNode):
        result = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        result = loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        result = loader.construct_mapping(node)
    else:
        raise "Bad value for {}".format(tag_suffix)

    return {tag_suffix: result}


def insert_cft_in_document(template, step_name, cft_template):
    assert len(cft_template) < 51200, "CloudFormation template too long, must be less then 50000"
    for step in template["mainSteps"]:
        if step["name"] == step_name:
            step["inputs"]["TemplateBody"] = cft_template
            break


def open_cloud_formation_template(file_name):
    with open(file_name) as fp:
        file_content = fp.read()

        return yaml.load(file_content, Loader=yaml.Loader)


def insert_script(config_json, document):
    if not os.path.exists(OUTPUT_PATH):
        os.makedirs(OUTPUT_PATH)

    output_file = "Output/{}.json".format(document['documentName'])
    automation_document_path = "{}/{}.json".format(document['documentFolder'], document['documentName'])

    with open(automation_document_path) as json_file:
        automation_document = json.load(json_file)

    if config_json is not None:
        for insert_step in config_json['build']:
            insert_type = insert_step['type']
            step_name = insert_step["stepName"]
            script_name = "{}/{}".format(document['documentFolder'], insert_step["file"])
            step_found = False

            for step in automation_document["mainSteps"]:
                if step["name"] == step_name:
                    step_found = True

                    if insert_type == "Command":
                        step["inputs"]["Parameters"]["commands"] = []
                        with open(script_name, 'r') as f:
                            for line in f:
                                step["inputs"]["Parameters"]["commands"] += \
                                    [line.replace('\n', '').replace('\r', '').replace('\t', '    ')]

                    elif insert_type == "CloudFormation":
                        step["inputs"]["TemplateBody"] = []

                        template = open_cloud_formation_template(script_name)
                        step["inputs"]["TemplateBody"] = yaml.safe_dump(template, indent=2)

            if step_found is False:
                print("Step: {} was not found.".format(step_name))

    with open(output_file, 'w+') as file:
        print("insert_script: building output file to {}".format(output_file))
        json.dump(automation_document, file)

    return automation_document


def build_ssm_documents(build_documents_config, build_graph=True):
    if build_documents_config:
        for document in build_documents_config['documents']:
            try:
                print("build_ssm_documents: document {}".format(document))
                with open("{}/config.json".format(document['documentFolder'])) as config:
                    config_json = json.load(config)
                    document_built = insert_script(config_json, document)
            except FileNotFoundError:
                document_built = insert_script(None, document)

            if document_built:
                if build_graph:
                    build_ssm_graph(document['documentName'], document_built)


def build_ssm_graph(document_name, document):
    print("build_ssm_graph: document_name {}".format(document_name))
    ssm_graph_builder = ssm_client.SSMClient()
    ssm_graph = ssm_graph_builder.convert_document_to_dot_graph(document)

    graph_output_path = "Output/{}.dot".format(document_name)
    print("build_ssm_documents: saving graph to {}".format(graph_output_path))

    with open(graph_output_path, "w") as text_file:
        text_file.write(ssm_graph)


def upload_ssm_artifacts(output_path="Output", bucket="ssm-automation"):
    output_artifacts = os.listdir(output_path)

    for output in output_artifacts:
        output_file = "Output/{}".format(output)
        print("upload_ssm_artifacts: uploading {}".format(output_file))

        try:
            response = s3_client.upload_file(output_file, bucket, output)
            print("upload_ssm_artifacts: uploaded {} successfully".format(output_file))
        except ClientError as e:
            print(e)


if __name__ == "__main__":
    yaml.add_multi_constructor("!", aws_tag_multi_constructor)

    with open(BUILD_CONFIG) as build_config:
        build_config_json = json.load(build_config)

    with open(PERMISSIONS_CONFIG) as permissions_config:
        permissions_config_json = json.load(permissions_config)

    build_ssm_documents(build_config_json, build_graph=True)

    ssm_object = ssm_client.SSMClient()
    ssm_object.check_ssm_documents()
    ssm_object.update_ssm_sharing_permissions(permissions_config_json['documents'])

    upload_ssm_artifacts()

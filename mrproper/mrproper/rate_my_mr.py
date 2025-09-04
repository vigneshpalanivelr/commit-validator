import requests
import argparse
from prettytable import PrettyTable
import re
import json
from .loc import LOCCalculator
from .params import RMMConstants, RMMWeights, RMMLimits


def print_banner(title):
    banner = "=" * 90  # Adjust the length as needed
    print(f"{banner}\n{title.center(90)}\n{banner}")


def send_request(payload, url=RMMConstants.agent_url.value):
    print(f"[DEBUG] AI Service Request - URL: {url}")
    print(f"[DEBUG] AI Service Request - Payload size: {len(str(payload))} chars")
    print(f"[DEBUG] AI Service Request - Timeout: 120 seconds")
    
    try:
        print("[DEBUG] Sending POST request to AI service...")
        resp = requests.post(url, json=payload, timeout=120)
        print(f"[DEBUG] AI Service Response - Status Code: {resp.status_code}")
        print(f"[DEBUG] AI Service Response - Content Length: {len(resp.content)}")
        
        # Raise an error for bad responses (4xx and 5xx)
        resp.raise_for_status()
        
        response_json = resp.json()
        print(f"[DEBUG] AI Service Response - JSON parsed successfully")
        return resp.status_code, response_json
        
    except requests.exceptions.HTTPError as http_err:
        print(f"[DEBUG] AI Service HTTP Error: {http_err}")
        print(f"[DEBUG] Response content: {resp.content[:500] if 'resp' in locals() else 'No response'}")
        return resp.status_code, str(http_err)
        
    except requests.exceptions.ConnectionError as conn_err:
        print(f"[DEBUG] AI Service Connection Error: {conn_err}")
        print("[DEBUG] This suggests the AI service is not reachable")
        return None, f"Connection failed: {str(conn_err)}"
        
    except requests.exceptions.Timeout as timeout_err:
        print(f"[DEBUG] AI Service Timeout Error: {timeout_err}")
        print("[DEBUG] AI service took longer than 120 seconds to respond")
        return None, f"Timeout after 120s: {str(timeout_err)}"
        
    except requests.exceptions.RequestException as req_err:
        print(f"[DEBUG] AI Service Request Error: {req_err}")
        print(f"[DEBUG] Error type: {type(req_err).__name__}")
        return None, str(req_err)
        
    except Exception as err:
        print(f"[DEBUG] AI Service Unexpected Error: {err}")
        print(f"[DEBUG] Error type: {type(err).__name__}")
        return False, str(err)


def generate_summary(file_path):
    # parser = argparse.ArgumentParser(
    #     description="Test Claude microservice with messages and optional thinking"
    # )
    # # Use parse_known_args so we can ignore Jupyter's '-f' if accidentally run in notebook
    # args, _ = parser.parse_known_args()
    # url = args.url if hasattr(args, 'url') else "http://10.31.88.29:6006/generate"

    # Read the git diff output from a file
    with open(file_path, 'r') as file:
        diff_output = file.read()
    payload1 = {
        "messages": [
            {"role": "system", "content": "You are a summarizer. Provide a concise summary of the git diff output."},
            {"role": "user", "content": diff_output}
        ]
    }
    # return send_request(url, payload1)
    status_code, code_summary = send_request(payload1)
    print_banner("Summary of the Merge Request")
    if status_code != 200:
        print(f"Failed to generate summary: {code_summary}")
    else:
        content = code_summary.get('content')[0]
        content_type = content.get('type')
        content_body = content.get(content_type)
        print(content_body)
        print("\n")
    return True, None


def generate_initial_code_review(file_path):
    with open(file_path, 'r') as file:
        diff_output = file.read()
    payload1 = {
        "messages": [
            {"role": "system", "content": ("You are a code reviewer tasked with evaluating the following code. Please analyze it thoroughly and provide detailed feedback, focusing on the following aspects:"
                                           "Bugs: Identify any potential bugs or logical errors in the code."
                                           "Code Quality: Suggest improvements for code readability, maintainability, and adherence to best practices."
                                           "Security Concerns: Highlight any security vulnerabilities or risks present in the code."
                                           "Performance: Point out any inefficiencies or areas where performance could be optimized."
                                           "Please provide specific examples from the code to support your comments and suggestions"
                                           )},
            {"role": "user", "content": diff_output}
        ]
    }
    # return send_request(url, payload1)
    print_banner("Initial Review")
    status_code, initial_review = send_request(payload1)
    if status_code != 200:
        print(f"Failed to generate summary: {initial_review}")
    else:
        content = initial_review.get('content')[0]
        content_type = content.get('type')
        content_body = content.get(content_type)
        print(content_body)
        print("\n")
    return True, None


def generate_lint_disable_report(file_path):
    try:
        with open(file_path, 'r') as file:
            diff_output = file.read()
        payload1 = {
            "messages": [
                {"role": "system", "content": ("Please analyze the following git diff output and extract all instances of # pylint: disable= comments. For each instance, provide a summary that includes:"
                                               "The specific pylint checks being disabled."
                                               "The lines of code they are associated with."
                                               "Any context or reasoning for why these disables might have been implemented."
                                               "Additionally, please count and report the total number of instances where pylint disables have been applied in this diff"
                                               "lines starts with single + is added and single - is removed"
                                               "nulliify if same is removed and added in another place for same function"
                                               "Also give report only added lints in json {\"num_lint_disable\": <number>, \"lints_that_disabled\":lints that disabled in commaseparated}")},
                {"role": "user", "content": diff_output}
            ]
        }
        status_code, lint_disbale = send_request(payload1)
        print_banner("Lint Disable report")
        if status_code != 200:
            print(f"Failed to generate lint disable report: {lint_disbale}")
        else:
            content = lint_disbale.get('content')[0]
            content_type = content.get('type')
            content_body = content.get(content_type)
            pattern = r'\{[^{}]*"num_lint_disable":\s*(\d+),\s*"lints_that_disabled":\s*"([^"]*)"[^{}]*\}'
            print(content_body)
            match = re.search(pattern, content_body)
            json_data = {}
            # Check if a match was found and print the result
            if match:
                json_data = match.group(0)
                json_data = json.loads(json_data)
                return True, json_data
            return False, "No data is available"
    except Exception as err:
        return False, str(err)


def cal_rating(total_loc, lint_disable_count):
    print_banner("Effective Rating Report")
    total_rating = RMMWeights.TOTAL_WEIGHT.value
    if total_loc > RMMLimits.MAX_LOC.value:
        total_rating -= RMMWeights.MAX_LOC.value
    if lint_disable_count > 0:
        total_rating -= RMMWeights.LINT_DISABLE.value
    table = PrettyTable()
    table.field_names = ["Metric", "Expected", "Actual", "Rating"]
    table.add_row(["Lines of Code", f"<= {RMMLimits.MAX_LOC.value}", total_loc, RMMWeights.MAX_LOC.value if total_loc <= RMMLimits.MAX_LOC.value else 0])
    table.add_row(["Lint Disables", "0", lint_disable_count, RMMWeights.LINT_DISABLE.value if lint_disable_count == 0 else 0])
    table.add_row(["------------------", "----------", "--------", "--------"])
    effective_rating = max(total_rating, 0)
    table.add_row(["Effectibe rating",  RMMWeights.TOTAL_WEIGHT.value, "", effective_rating])
    print(table)

    return effective_rating


def main():
    parser = argparse.ArgumentParser(
        description="Rate my MR required parameters"
    )
    parser.add_argument('filename', type=str, help='The name of the file to process')
    args, _ = parser.parse_known_args()
    status_code, commit_summary = generate_summary(args.filename)
    status_code, review_comments = generate_initial_code_review(args.filename)

    print_banner("LOC Summary")
    loc_cal = LOCCalculator(args.filename)
    success, loc_data = loc_cal.calculate_loc()
    if not success:
        print(f"Failed to calculate LOC: {loc_data}")
    print("\n"*2)
    success, lint_disbale = generate_lint_disable_report(args.filename)
    if not success:
        print(f"Failed to generate lint disable report: {lint_disbale}")
    print("\n"*2)
    cal_rating(loc_data.get('net_lines_of_code_change'), lint_disbale.get('num_lint_disable'))


if __name__ == "__main__":
    main()

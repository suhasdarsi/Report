import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Union

def get_risk_score(risk_level: str) -> int:
    return {'High': 3, 'Medium': 2, 'Low': 1}.get(risk_level, 0)

def load_risk_table(json_file: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    try:
        with open(json_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {json_file}: {str(e)}")
        return []
    except FileNotFoundError:
        print(f"File not found: {json_file}")
        return []

def find_risk_data(risk_data: Union[List[Dict[str, Any]], Dict[str, Any]], question: str) -> Tuple[Dict[str, Any], int]:
    if isinstance(risk_data, dict):
        return risk_data.get(question, {}), None
    elif isinstance(risk_data, list):
        for i, item in enumerate(risk_data):
            if item.get('Question') == question:
                return item, i
    return {}, None


def process_vendor_data(data: Any, risk_data: Union[List[Dict[str, Any]], Dict[str, Any]], vendor_name: str, filename: str) -> Dict[str, Any]:
    combined_data = defaultdict(lambda: {'question': '', 'category': '', 'sub_category': '', 'risk_level': '', 'expected_outcome': '', 'answers': {}})
    vendor_risk_score = 0
    max_possible_score = 0
    category_scores = defaultdict(float)
    missed_controls = []

    items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []

    for item in items:
        try:
            if isinstance(item, str):
                question, answer = item.strip(), data[item]
            elif isinstance(item, dict):
                question, answer = item.get('Question', '').strip(), item.get('Answer', '')
            else:
                continue

            risk_info, risk_info_idx = find_risk_data(risk_data, question)
            if not risk_info:
                print(f"Warning: Question '{question}' not found in risk data. Adding it with default values. File: {filename}")
                risk_info = {
                    'Category': 'Unknown',
                    'Sub Category': 'Unknown',
                    'Risk Level': 'Medium',
                    'Expected': 'Yes'
                }

            combined_data[question] = {
                'question': question,
                'category': risk_info.get('Category', 'Unknown'),
                'sub_category': risk_info.get('Sub Category', 'Unknown'),
                'risk_level': risk_info.get('Risk Level', 'Medium'),
                'expected_outcome': risk_info.get('Expected', 'Yes'),
                'answers': {vendor_name: answer}
            }

            risk_score = get_risk_score(risk_info.get('Risk Level', 'Medium'))
            if answer != risk_info.get('Expected', 'Yes'):
                vendor_risk_score += risk_score
                category_scores[risk_info.get('Category', 'Unknown')] += risk_score
                missed_controls.append(question)

            max_possible_score += risk_score
        except Exception as e:
            print(f"Error processing question in file {filename}: {str(e)}")
            print(f"Problematic item: {item}")

    percentage_risk_score = (vendor_risk_score / max_possible_score) * 100 if max_possible_score > 0 else 0

    return {
        'combined_data': combined_data,
        'vendor_risk_score': round(percentage_risk_score, 2),
        'category_scores': category_scores,
        'missed_controls': missed_controls
    }

def combine_json_files_with_scores(folder_path: str, risk_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    combined_data = defaultdict(lambda: {'question': '', 'category': '', 'sub_category': '', 'risk_level': '', 'expected_outcome': '', 'answers': {}})
    combined_data['system_risk_scores'] = {}
    combined_data['category_scores'] = defaultdict(lambda: defaultdict(float))
    combined_data['missed_controls_frequency'] = defaultdict(int)

    for filename in os.listdir(folder_path):
        if filename.endswith('.json'):
            file_path = os.path.join(folder_path, filename)
            vendor_name = os.path.splitext(filename)[0]

            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    data = json.load(file)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON in file {filename}: {str(e)}")
                continue
            except FileNotFoundError:
                print(f"File not found: {filename}")
                continue
            except Exception as e:
                print(f"Unexpected error processing file {filename}: {str(e)}")
                continue

            try:
                result = process_vendor_data(data, risk_data, vendor_name, filename)
                for key in result['combined_data'].keys():
                    combined_data[key]['answers'][vendor_name] = result['combined_data'][key]['answers'][vendor_name]
                    combined_data[key]['question'] = result['combined_data'][key]['question']
                    combined_data[key]['category'] = result['combined_data'][key]['category']
                    combined_data[key]['sub_category'] = result['combined_data'][key]['sub_category']
                    combined_data[key]['risk_level'] = result['combined_data'][key]['risk_level']
                    combined_data[key]['expected_outcome'] = result['combined_data'][key]['expected_outcome']
                # combined_data.update(result['combined_data'])
                combined_data['system_risk_scores'][vendor_name] = result['vendor_risk_score']
                combined_data['category_scores'][vendor_name] = result['category_scores']

                for control in result['missed_controls']:
                    combined_data['missed_controls_frequency'][control] += 1
            except Exception as e:
                print(f"Error processing data for vendor {vendor_name} in file {filename}: {str(e)}")

    return combined_data

def calculate_metrics(combined_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        all_scores = list(combined_data['system_risk_scores'].values())
        avg_risk_score = sum(all_scores) / len(all_scores) if all_scores else 0
        highest_risk_vendor = max(combined_data['system_risk_scores'], key=combined_data['system_risk_scores'].get)
        lowest_risk_vendor = min(combined_data['system_risk_scores'], key=combined_data['system_risk_scores'].get)

        control_scores = defaultdict(list)
        for question, info in combined_data.items():
            if isinstance(info, dict) and 'answers' in info:
                for vendor, answer in info['answers'].items():
                    if answer != info['expected_outcome']:
                        control_scores[question].append(vendor)

        highest_risk_control = max(control_scores, key=lambda x: len(control_scores[x])) if control_scores else None
        lowest_risk_control = min(control_scores, key=lambda x: len(control_scores[x])) if control_scores else None

        top_5_risks = sorted(control_scores, key=lambda x: len(control_scores[x]), reverse=True)[:5]
        top_control_missed = top_5_risks[0] if top_5_risks else None
        top_control_satisfied = min(control_scores, key=lambda x: len(control_scores[x])) if control_scores else None

        category_avg_scores = defaultdict(list)
        for vendor, categories in combined_data['category_scores'].items():
            for category, score in categories.items():
                category_avg_scores[category].append(score)

        category_avg_scores = {cat: sum(scores) / len(scores) for cat, scores in category_avg_scores.items()}
        top_category_failing = max(category_avg_scores, key=category_avg_scores.get)
        top_category_passed = min(category_avg_scores, key=category_avg_scores.get)

        controls_missed_frequency = combined_data['missed_controls_frequency']
        top_5_missed_controls = sorted(controls_missed_frequency.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            'average_risk_score': round(avg_risk_score, 2),
            'highest_risk_vendor': highest_risk_vendor,
            'lowest_risk_vendor': lowest_risk_vendor,
            'highest_risk_control': highest_risk_control,
            'lowest_risk_control': lowest_risk_control,
            'top_5_risks': top_5_risks,
            'top_control_missed': top_control_missed,
            'top_control_satisfied': top_control_satisfied,
            'category_avg_scores': category_avg_scores,
            'top_category_failing': top_category_failing,
            'top_category_passed': top_category_passed,
            'top_5_missed_controls': top_5_missed_controls
        }
    except Exception as e:
        print(f"Error calculating metrics: {str(e)}")
        return {}

def main():
    try:
        folder_path = './reportv3'  # Replace with the actual path to your folder
        json_file = 'risk_table.json'  # Load data from the JSON file
        risk_data = load_risk_table(json_file)
        if not risk_data:
            print(f"Error: Unable to load risk data from {json_file}")
            return

        combined_data = combine_json_files_with_scores(folder_path, risk_data)
        metrics = calculate_metrics(combined_data)

        result = {
            'questions': [
                {
                    'question': info['question'],
                    'category': info['category'],
                    'sub_category': info['sub_category'],
                    'risk_level': info['risk_level'],
                    'expected_outcome': info['expected_outcome'],
                    'answers': info['answers']
                }
                for info in combined_data.values() if isinstance(info, dict) and 'question' in info
            ],
            'system_risk_scores': combined_data['system_risk_scores'],
            'missed_controls_frequency': combined_data['missed_controls_frequency'],
            **metrics
        }

        output_file = 'combined_ai_systems_with_risk_scores.json'
        with open(output_file, 'w', encoding='utf-8') as outfile:
            json.dump(result, outfile, indent=2, ensure_ascii=False)
        print(f"Combined JSON file created: {output_file}")
    except Exception as e:
        print(f"An error occurred in the main function: {str(e)}")

if __name__ == "__main__":
    main()

#from langchain_community.chat_models import ChatOllama
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
import os       # для работы с директориями и файлами
import json
import regex as re # для работы с регулярными выражениям
import sys  # доступ к аргументам командной строки
from collections import defaultdict # позволяет создавать словарь, который автоматически создаёт значения
                                    # по умолчанию для несуществующих ключей.
from typing import List, Dict, Union, Optional # для type hints (аннотации типов)
from langchain_openai import ChatOpenAI  # для интеграции с помощью OpenRouter

class TcpAnalysisOutput:
    tcp_functions: list[str]
    constants: list[str]
    issues: list[str]


class TCPFunction(BaseModel):
    function_name: str
    type: str
    file: str
    line: int

                    # принимает один аргумент типа str, возвращает список кортежей
def find_source_files(path: str) -> List[tuple]: # Рекурсивно находит все .c, .cpp, .h файлы в директории
                                                 # и возвращает список кортежей (путь_к_файлу, содержимое)
    if os.path.isfile(path):
        if path.endswith(('.c', '.cpp', '.h')):  # проверяет формат
            try:
                with open(path, 'r', encoding='utf-8') as f:  # with автоматически закрывает файл  
                    return [(path, f.read())]                 # после выхода из блока

            except Exception as e:
                print(f"Error reading file {path}: {e}")
        return []
    
    source_files = []
    for root, _, files in os.walk(path):         # os.walk() рекурсивно проходит по всем подкаталогам.
        for file_name in files:
            if file_name.endswith(('.c', '.cpp', '.h')):
                file_path = os.path.join(root, file_name) # правильно склеивает пути для Linux, Windows и тд
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        source_files.append((file_path, f.read()))
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    return source_files


def load_prompt(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()


def add_line_numbers(code, filename):
    lines = code.splitlines()           # разбивает его на список строк по переносам строк (\n).
    numbered_lines = [f"{i+1}: {line}" for i, line in enumerate(lines)] # [expression for variables in iterating obj if condition]
    return f"// File: {filename}\n" + "\n".join(numbered_lines) # Все строки из numbered_lines соединяются
                                                                # через \n (перевод строки)



def extract_json(text: str) -> Union[List, Dict, None]:

    matches = re.findall(r'\{(?:[^{}]|(?R))*\}|\[(?:[^[\]]|(?R))*\]', text, flags=re.DOTALL)
    """                                                                     Точка . — совпадает со всеми символами,
    Разбор регулярного выражения                                            кроме перевода строки  (\n),  DOTALL - включает   
    1. r'...' - raw string, позволяет использовать \\ как обычный символ
    2.\\{...\\} - поиск JSON-объекта {...}
    3. (?:...) — группа без захвата (не сохраняет результат в отдельную группу), если ... есть - пропустит
    4. [^}] — любой символ, кроме }, в нашей строке еще и без {
    5. | — или
    6. (?R) — рекурсивно применить всё регулярное выражение целиком
    7. * - повторять 0 или более раз
    """
    results = []
    for match in matches:
        try:
            results.append(json.loads(match)) # конвертирует объекты json в соответствующие объекты python
        except json.JSONDecodeError:
            continue
    return results[0] if len(results) == 1 else results if results else None # Если найден один объект - вернуть как 
                                                                             # словарь или список.
                                                                             # Если несколько — вернуть список
                                                                             # JSON-объектов.
                                                                             # Иначе - None.

def print_functions(functions: List[Dict]) -> None:

    if not functions:
        print("No TCP functions found")
        return

    grouped = defaultdict(list) # группировка по типу
    for func in functions:
        if isinstance(func, dict):
            grouped[func.get('type', 'unknown')].append(func) # получаем значение по ключу 'type',
                                                              # если его нет — возвращаем 'unknown',
                                                              # затем добавляем в группу
    # настройки цветов
    try:
        from termcolor import colored   # функция, которая добавляет цвет и стили к строке текста
        COLORS = {
            'handler': 'green',
            'parser': 'blue',
            'validator': 'yellow',
            'unknown': 'magenta'        # в python можно объявлять функцию вот так
        }                               # и COLORS в той же области видимости

        def colorize(text, color_type):
            return colored(text, COLORS.get(color_type, 'magenta'), attrs=['bold'])

    except ImportError:
        colorize = lambda text, _: text # лямбда-функция, которая возвращает переданный текст без изменений 
                                        # _ значит, что второй аргумент игнорируется

    # Вывод
    border = "=" * 60
    print(f"\n{border}")
    print(colorize("TCP FUNCTIONS ANALYSIS", 'unknown'))
    print(border)

    for func_type, items in grouped.items(): # .items() возвращает пары "ключ-значение" из словаря  как список кортежей.
        print(f"\n{colorize(f'{func_type.upper()}:', func_type)}")
        for func in items:
            print(f"  ├─ {colorize(func['function_name'], func_type)}")
            print(f"  │  ├─ File: {func['file']}")
            print(f"  │  └─ Line: {func['line']}")

    print(f"\n{border}")
    print(colorize(f"TOTAL: {len(functions)} functions", 'unknown'))
    print(border)


if __name__ == "__main__":      # Жалкая пародия на C/C++, когда не делаешь main по дефолту
    import sys                  # Доступ к аргументам командной строки

    if len(sys.argv) != 2:
        print("Wrong input format. Must be: python3 this_script.py  <путь_к_директории>")
        sys.exit(1)

    project_dir = sys.argv[1]
    if not os.path.exists(project_dir):
        print(f"Path does not exist: {project_dir}")
        sys.exit(1)

    files = find_source_files(project_dir)
    
    if not files:
        print("[-] No source files found in directory")
        sys.exit(1)

    os.environ["OPENROUTER_API_KEY"] = "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"
    model = ChatOpenAI(
            model="openrouter/cypher-alpha:free", 
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
            temperature=0.5     # поскольку задача требует строгости соблюдения требований запроса
            )
    #model = ChatOllama(model="llama3")
    prompt_text = load_prompt("Prompts/TCP_functions_request.txt")  
    prompt = ChatPromptTemplate.from_template(prompt_text)

    # Получение кода с номерами строк
    all_files_code = "\n".join([add_line_numbers(content, path) for path, content in files])

    # Запрос к модели
    response = (prompt | model).invoke({"code": all_files_code})
    print("\n=== Raw Model Output ===\n")
    print(response.content)

    # Извлечение JSON
    json_output = extract_json(response.content)
    if not json_output:
        print("No valid JSON found in response")
        sys.exit(1)

    # Отладочный вывод структуры JSON
    print("\n=== Parsed JSON Structure ===")
    print(json_output)

    functions = []
    if isinstance(json_output, dict):
        for key in ['functions', 'tcp_functions']:
            if key in json_output and isinstance(json_output[key], list):
                functions.extend([
                    f for f in json_output[key] 
                    if isinstance(f, dict) and 'function_name' in f
                ])
    elif isinstance(json_output, list):
        functions = [
            f for f in json_output 
            if isinstance(f, dict) and 'function_name' in f
        ]

    # Вывод результатов
    if functions:
        print_functions(functions)
    else:
        print("Found JSON but no valid TCP functions detected")
        print("Raw JSON output:")
        print(json.dumps(json_output, indent=2))


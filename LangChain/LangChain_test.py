from langchain_community.chat_models import ChatOllama      
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate       # Быстрые шаблоны LangChain для обработки текста
import asyncio

model = ChatOllama(model="llama3")      # Подключаем модель

"""                     # Этот способ задает фиксированный список строк, нельзя менять, только заново пересоздавать
messages = [
    SystemMessage(content="Translate the following from English into Italian"),     # системные сообщения
    HumanMessage(content="hi!"),                                                    # сообщения пользователя
    # AIMessage(...),                                                               # сообщения LLM
]
"""

#response = model.invoke(messages)
#print(response.content)

"""                 # Как написано в статье, можно короче записать ChatPromptTemplate()
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are translating from English into {language}"),
    ("human", "{text}")
])

prompt = ChatPromptTemplate([
    ("system", "You are translating from English into {language}"),
    ("human", "{text}")
])
"""

# Методы и что возвращается Prompts и модель (как это работате в пэтхоне (python))

"""
1. .invoke() - возвращает Объект ChatPromptValue, который можно передать в модель model.invoke(prompt_value)
    
    prompt_value = prompt.invoke({"name": "Mihail", "user_input": "What is your name?"})
    
    response = model.invoke([HumanMessage(content="Привет!")])
    print(response.content)

2. .format_messages() - просто список сообщений

    messages = prompt.format_messages(name="Alice", user_input="Hi!")
    print(messages)

    Вывод что-то вроде:
    [
        SystemMessage(content='You are a helpful assistant named Alice'),
        HumanMessage(content='Hi!')
    ]

3. .stream() - потоковая обработка, возвращает AIMessageChunk, в котором есть .content - часть текстового ответа.
    Ну и другая инфа, в статье там есть

    for token in model.stream(prompt.invoke({"language": "French", "text": "Hello world"})):
        print(token.content, end="|")

4. .partial() - предварительное заполнение переменных
    partial_prompt = prompt.partial(name="Mihail")
    response = partial_prompt.invoke({"user_input": "How are you?"})

5. .save(), load_prompt() — сохранение и загрузка

    prompt.save("translation_prompt.json")

    и потом 

    from langchain_core.prompts import load_prompt
    loaded_prompt = load_prompt("translation_prompt.json")

6. .batch(inputs) — пакетная обработка, возвращает список AIMessage, по одному на каждый элемент из inputs.
    messages_list = [
        [HumanMessage(content="You are translating from English into French")],
        [HumanMessage(content="How are you?")]
    ]
    responses = model.batch(messages_list)

    for res in responses:
        print(res.content)
"""

# 1. invoke()
print("invoke():", model.invoke([HumanMessage(content="Привет!")]).content)

"""
# 2. stream()
print("\nstream():")
for chunk in model.stream([HumanMessage(content="Расскажи историю про кота")]):
    print(chunk.content, end="", flush=True)
"""

# 3. batch()
print("\n\nbatch():")
results = model.batch([
    [HumanMessage(content="Переведи 'hi' на французский")],
    [HumanMessage(content="Сколько будет 2+2?")]
])
for r in results:
    print(r.content)

"""
# 4. with_retry()
retry_model = model.with_retry(stop_after_attempt=3)
print("\nwith_retry():")
try:
    retry_model.invoke([HumanMessage(content="Сгенерируй длинный текст")])
except Exception as e:
    print("Ошибка после 3 попыток")
"""

# 5. astream_events()
async def events():
    async for ev in model.astream_events([HumanMessage(content="Ты шаришь за физику? Если да, то объясни, что такое распределение Больцмана и напиши уравнение Соаве-Редлиха-Квонга")], version="v2"):
        if "chunk" in ev["data"]:
            print(ev["data"]["chunk"].content, end="", flush=True)

print("\n\nastream_events():")
asyncio.run(events())


# encoding=utf-8
"""
BytePlus Responses API 缓存功能测试脚本

测试通过 OpenAI 协议调用 BytePlus/字节跳动 Seed 模型的 Responses API，
验证 extra_body 中的 caching 和 thinking 参数是否正确传递。

使用方法:
    python test_byteplus_responses_cache.py

环境变量:
    - NEW_API_BASE_URL: API 基础 URL (默认: http://localhost:3000)
    - NEW_API_KEY: API 密钥
    - BYTEPLUS_MODEL: 模型名称 (默认: seed-1-6-250915)

参考文档:
    - BytePlus Responses API: https://docs.byteplus.com/en/docs/ModelArk/Create_model_request
"""

import os
import json
import time
import requests
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

# 配置
BASE_URL = os.getenv('NEW_API_BASE_URL', 'http://localhost:3000')
API_KEY = os.getenv('NEW_API_KEY', 'sk-test')
MODEL = os.getenv('BYTEPLUS_MODEL', 'seed-1-6-250915')


@dataclass
class TokenDetails:
    cached_tokens: int = 0
    reasoning_tokens: int = 0

@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_tokens_details: Optional[TokenDetails] = None
    output_tokens_details: Optional[TokenDetails] = None

@dataclass
class Response:
    id: str
    status: str
    output: List[Dict]
    usage: Optional[Usage] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Response':
        usage = None
        if 'usage' in data:
            u = data['usage']
            input_details = None
            output_details = None
            if 'input_tokens_details' in u:
                input_details = TokenDetails(
                    cached_tokens=u['input_tokens_details'].get('cached_tokens', 0)
                )
            if 'output_tokens_details' in u:
                output_details = TokenDetails(
                    reasoning_tokens=u['output_tokens_details'].get('reasoning_tokens', 0)
                )
            usage = Usage(
                input_tokens=u.get('input_tokens', 0),
                output_tokens=u.get('output_tokens', 0),
                total_tokens=u.get('total_tokens', 0),
                input_tokens_details=input_details,
                output_tokens_details=output_details
            )
        return cls(
            id=data.get('id', ''),
            status=data.get('status', ''),
            output=data.get('output', []),
            usage=usage
        )


def responses_create(
    model: str,
    input_messages: List[Dict],
    thinking: Optional[Dict] = None,
    caching: Optional[Dict] = None,
    previous_response_id: Optional[str] = None,
    stream: bool = False,
    timeout: int = 120
) -> Optional[Response]:
    """
    调用 Responses API
    """
    url = f"{BASE_URL}/v1/responses"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": input_messages,
        "stream": stream
    }
    
    if thinking:
        payload["thinking"] = thinking
    if caching:
        payload["caching"] = caching
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            return Response.from_dict(resp.json())
        else:
            print(f"Error: {resp.status_code} - {resp.text[:500]}")
            return None
    except Exception as e:
        print(f"Request error: {e}")
        return None


def responses_create_stream(
    model: str,
    input_messages: List[Dict],
    thinking: Optional[Dict] = None,
    caching: Optional[Dict] = None,
    previous_response_id: Optional[str] = None,
    timeout: int = 120
):
    """
    调用 Responses API (流式)
    """
    url = f"{BASE_URL}/v1/responses"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": input_messages,
        "stream": True
    }
    
    if thinking:
        payload["thinking"] = thinking
    if caching:
        payload["caching"] = caching
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout, stream=True)
        if resp.status_code == 200:
            for line in resp.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            yield json.loads(data_str)
                        except json.JSONDecodeError:
                            pass
        else:
            print(f"Error: {resp.status_code} - {resp.text[:500]}")
    except Exception as e:
        print(f"Request error: {e}")

def print_separator(title: str):
    """打印分隔线"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def print_usage(usage: Optional[Usage]):
    """打印 usage 信息"""
    if usage:
        print(f"  - Input Tokens: {usage.input_tokens}")
        print(f"  - Output Tokens: {usage.output_tokens}")
        print(f"  - Total Tokens: {usage.total_tokens}")
        if usage.input_tokens_details:
            print(f"  - Cached Tokens: {usage.input_tokens_details.cached_tokens}")
        if usage.output_tokens_details:
            print(f"  - Reasoning Tokens: {usage.output_tokens_details.reasoning_tokens}")

def get_output_text(response: Response) -> str:
    """从响应中提取输出文本"""
    if response.output:
        for output in response.output:
            if output.get('type') == 'message':
                content_list = output.get('content', [])
                for content in content_list:
                    if content.get('type') == 'output_text':
                        return content.get('text', '')
    return ''

def test_basic_responses():
    """测试基本的 Responses API 调用"""
    print_separator("Test 1: Basic Responses API")
    
    response = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "Hello, what is 2+2?"}
        ],
        thinking={"type": "disabled"}
    )
    
    if response is None:
        print("Error: Failed to get response")
        return None
    
    print(f"Response ID: {response.id}")
    print(f"Status: {response.status}")
    
    text = get_output_text(response)
    if text:
        print(f"Output: {text[:200]}...")
    
    print("\nUsage:")
    print_usage(response.usage)
    
    return response

def test_prefix_caching():
    """测试前缀缓存功能"""
    print_separator("Test 2: Prefix Caching")
    
    # 长文本输入（至少 256 tokens 才能创建缓存）
    long_context = """
You are a literary analysis assistant. Answer concisely and clearly.

Here is an excerpt from "The Gift of the Magi" by O. Henry:

One dollar and eighty-seven cents. That was all. And sixty cents of it was in pennies. 
Pennies saved one and two at a time by bulldozing the grocer and the vegetable man and 
the butcher until one's cheeks burned with the silent imputation of parsimony that such 
close dealing implied. Three times Della counted it. One dollar and eighty-seven cents. 
And the next day would be Christmas.

There was clearly nothing to do but flop down on the shabby little couch and howl. 
So Della did it. Which instigates the moral reflection that life is made up of sobs, 
sniffles, and smiles, with sniffles predominating.

While the mistress of the home is gradually subsiding from the first stage to the second, 
take a look at the home. A furnished flat at $8 per week. It did not exactly beggar 
description, but it certainly had that word on the lookout for the mendicancy squad.

In the vestibule below was a letter-box into which no letter would go, and an electric 
button from which no mortal finger could coax a ring. Also appertaining thereunto was a 
card bearing the name "Mr. James Dillingham Young."

The "Dillingham" had been flung to the breeze during a former period of prosperity when 
its possessor was being paid $30 per week. Now, when the income was shrunk to $20, though, 
they were thinking seriously of contracting to a modest and unassuming D. But whenever 
Mr. James Dillingham Young came home and reached his flat above he was called "Jim" and 
greatly hugged by Mrs. James Dillingham Young, already introduced to you as Della. Which 
is all very good.

Della finished her cry and attended to her cheeks with the powder rag. She stood by the 
window and looked out dully at a gray cat walking a gray fence in a gray backyard. 
Tomorrow would be Christmas Day, and she had only $1.87 with which to buy Jim a present. 
She had been saving every penny she could for months, with this result. Twenty dollars a 
week doesn't go far. Expenses had been greater than she had calculated. They always are. 
Only $1.87 to buy a present for Jim. Her Jim. Many a happy hour she had spent planning 
for something nice for him. Something fine and rare and sterling—something just a little 
bit near to being worthy of the honor of being owned by Jim.
"""
    
    print("Step 1: Creating initial response with prefix caching enabled...")
    
    # 第一次请求：启用前缀缓存
    response1 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "system", "content": long_context},
            {"role": "user", "content": "What is the main theme of this story?"}
        ],
        caching={"type": "enabled", "prefix": True},
        thinking={"type": "disabled"}
    )
    
    if response1 is None:
        print("Error: Failed to create initial response")
        return None, None
    
    print(f"Response 1 ID: {response1.id}")
    print("\nUsage (First Request):")
    print_usage(response1.usage)
    
    text = get_output_text(response1)
    if text:
        print(f"\nOutput: {text[:300]}...")
    
    # 等待缓存创建 - BytePlus 缓存需要较长时间来处理
    print("\nWaiting for cache to be created (15 seconds)...")
    time.sleep(15)
    
    # 第二次请求：使用 previous_response_id 利用缓存
    print("\nStep 2: Using previous_response_id to leverage cache...")
    response2 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "Who are the main characters?"}
        ],
        previous_response_id=response1.id,
        caching={"type": "enabled"},
        thinking={"type": "disabled"}
    )
    
    if response2 is None:
        print("Error: Failed to create second response")
        return response1, None
    
    print(f"Response 2 ID: {response2.id}")
    print("\nUsage (Second Request - Should show cached tokens):")
    print_usage(response2.usage)
    
    text2 = get_output_text(response2)
    if text2:
        print(f"\nOutput: {text2[:300]}...")
    
    # 检查缓存命中
    if response2.usage and response2.usage.input_tokens_details:
        cached = response2.usage.input_tokens_details.cached_tokens
        if cached > 0:
            print(f"\n[OK] Cache HIT! Cached tokens: {cached}")
        else:
            print("\n[WARN] No cache hit detected (cached_tokens = 0)")
    
    return response1, response2

def test_thinking_mode():
    """测试思考模式配置"""
    print_separator("Test 3: Thinking Mode Configuration")
    
    print("Testing with thinking disabled...")
    
    response = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "What is the square root of 144?"}
        ],
        thinking={"type": "disabled"}
    )
    
    if response is None:
        print("Error: Failed to get response")
        return None
    
    print(f"Response ID: {response.id}")
    print("\nUsage:")
    print_usage(response.usage)
    
    text = get_output_text(response)
    if text:
        print(f"\nOutput: {text}")
    
    return response

def test_streaming():
    """测试流式响应"""
    print_separator("Test 4: Streaming Response")
    
    print("Testing streaming with caching...")
    
    print("Streaming output:")
    full_text = ""
    final_usage = None
    
    for event in responses_create_stream(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "Count from 1 to 5."}
        ],
        thinking={"type": "disabled"}
    ):
        event_type = event.get('type', '')
        if event_type == 'response.output_text.delta':
            delta = event.get('delta', '')
            print(delta, end='', flush=True)
            full_text += delta
        elif event_type == 'response.completed':
            resp_data = event.get('response', {})
            if resp_data and 'usage' in resp_data:
                u = resp_data['usage']
                input_details = None
                output_details = None
                if 'input_tokens_details' in u:
                    input_details = TokenDetails(
                        cached_tokens=u['input_tokens_details'].get('cached_tokens', 0)
                    )
                if 'output_tokens_details' in u:
                    output_details = TokenDetails(
                        reasoning_tokens=u['output_tokens_details'].get('reasoning_tokens', 0)
                    )
                final_usage = Usage(
                    input_tokens=u.get('input_tokens', 0),
                    output_tokens=u.get('output_tokens', 0),
                    total_tokens=u.get('total_tokens', 0),
                    input_tokens_details=input_details,
                    output_tokens_details=output_details
                )
    
    if final_usage:
        print("\n\nFinal Usage:")
        print_usage(final_usage)
    
    print(f"\n\nFull text: {full_text}")
    return len(full_text) > 0

def generate_long_context(target_tokens: int = 130000) -> str:
    """
    生成超长上下文文本，用于测试分段计费
    
    Args:
        target_tokens: 目标 token 数量（默认 130K，超过 128K 阈值）
    
    Returns:
        生成的长文本
    """
    # 每个段落大约 200-300 tokens
    base_paragraph = """
In the realm of artificial intelligence and machine learning, the concept of context window 
has become increasingly important. Modern language models are designed to process and understand 
vast amounts of text, enabling them to maintain coherence across long documents and conversations. 
The ability to handle extended context is crucial for tasks such as document summarization, 
long-form content generation, and complex reasoning that requires understanding relationships 
between distant pieces of information.

The architecture of transformer-based models has evolved significantly since the introduction 
of the attention mechanism. Self-attention allows models to weigh the importance of different 
parts of the input when generating each output token. However, the computational complexity 
of standard attention grows quadratically with sequence length, which has historically limited 
the practical context window size. Recent innovations such as sparse attention, linear attention, 
and various compression techniques have helped overcome these limitations.

Context caching is a powerful optimization technique that allows models to reuse computations 
from previous requests. When a user sends multiple queries with overlapping context, the model 
can cache the key-value pairs from the shared prefix and only compute the new portions. This 
significantly reduces latency and computational costs, especially for applications involving 
long system prompts or multi-turn conversations with substantial context.

The economics of large language model inference are heavily influenced by context length. 
Longer contexts require more memory and computation, which translates to higher costs. 
Tiered pricing models have emerged as a way to balance accessibility with sustainability, 
offering lower per-token prices for shorter contexts while charging premium rates for 
extended context windows that require additional resources.
"""
    
    # 估算每个段落约 350 tokens，需要约 370 个段落达到 130K tokens
    paragraphs_needed = (target_tokens // 350) + 10
    
    sections = []
    topics = [
        "Natural Language Processing", "Computer Vision", "Reinforcement Learning",
        "Neural Networks", "Deep Learning", "Machine Translation", "Speech Recognition",
        "Sentiment Analysis", "Named Entity Recognition", "Question Answering",
        "Text Generation", "Image Classification", "Object Detection", "Semantic Segmentation",
        "Generative Adversarial Networks", "Variational Autoencoders", "Attention Mechanisms",
        "Transfer Learning", "Few-Shot Learning", "Zero-Shot Learning", "Meta-Learning",
        "Federated Learning", "Continual Learning", "Multi-Task Learning", "Self-Supervised Learning"
    ]
    
    for i in range(paragraphs_needed):
        topic = topics[i % len(topics)]
        section_num = i + 1
        
        section = f"""
=== Section {section_num}: {topic} ===

{base_paragraph}

In the context of {topic}, researchers have made significant strides in developing more 
efficient and effective algorithms. The field continues to evolve rapidly, with new 
breakthroughs emerging regularly. Key challenges include improving model efficiency, 
reducing training costs, and ensuring that AI systems are safe, fair, and beneficial 
to society. The intersection of {topic} with other domains has opened up exciting new 
possibilities for real-world applications.

Technical considerations for {topic} include data preprocessing, feature engineering, 
model selection, hyperparameter tuning, and evaluation metrics. Practitioners must 
carefully balance trade-offs between model complexity and interpretability, training 
time and inference speed, and generalization ability and task-specific performance. 
The choice of architecture and training strategy can significantly impact the final 
results, making experimentation and iteration essential parts of the development process.

"""
        sections.append(section)
    
    return "\n".join(sections)


def generate_long_context_literature(target_tokens: int = 200000) -> str:
    """
    生成文学作品风格的超长上下文文本
    
    Args:
        target_tokens: 目标 token 数量（默认 200K）
    
    Returns:
        生成的长文本
    """
    # 文学风格的基础段落，每段约 400 tokens
    story_templates = [
        """
Chapter {chapter}: The Journey Begins

The morning sun cast long shadows across the ancient cobblestone streets as our protagonist 
set forth on what would become the most remarkable adventure of their lifetime. The air was 
thick with the scent of blooming jasmine, and somewhere in the distance, church bells tolled 
the hour with a solemnity that seemed to mark this moment as significant.

In the small village of Thornwood, nestled between rolling hills and dense forests that had 
stood for centuries, life had always moved at a measured pace. The villagers knew each other 
by name, their families intertwined through generations of shared history, marriages, and 
the occasional feud that would simmer for decades before being resolved over a pint at the 
local tavern.

But change was coming to Thornwood, as it inevitably comes to all places that have grown 
too comfortable in their isolation. The railroad had been extended, bringing with it 
strangers from the city who spoke of progress and opportunity. Some villagers welcomed 
these newcomers with open arms, eager to hear tales of the wider world. Others viewed them 
with suspicion, sensing that their arrival heralded the end of a way of life that had 
sustained their community for generations.

Our hero, young and idealistic, stood at the crossroads of these two worlds. Born to a 
family of modest means but blessed with an insatiable curiosity and a heart full of 
dreams, they had always felt that destiny had something greater in store for them than 
a life confined to the boundaries of Thornwood.
""",
        """
Chapter {chapter}: Secrets Unveiled

The old library stood at the edge of town, its weathered facade a testament to the 
countless storms it had weathered over the centuries. Within its walls lay treasures 
beyond measure - not gold or jewels, but knowledge accumulated over generations, 
preserved in leather-bound volumes that lined shelves reaching toward vaulted ceilings.

It was here that our protagonist discovered the first clue to the mystery that would 
consume their thoughts for months to come. Hidden within the pages of an unremarkable 
tome on local history was a letter, yellowed with age, its ink faded but still legible 
to those patient enough to decipher its cramped handwriting.

The letter spoke of a secret society that had operated in Thornwood during the turbulent 
years of the previous century. Its members, drawn from the most influential families in 
the region, had sworn an oath to protect something of immense value - though the nature 
of this treasure was described only in the vaguest terms.

What caught our hero's attention was not the promise of hidden riches, but the mention 
of a name that had haunted their family for generations. Could it be that their own 
ancestors had been involved in this clandestine organization? And if so, what secrets 
had they carried to their graves?

The investigation that followed would lead our protagonist down paths they never 
imagined walking, into the company of allies both trustworthy and treacherous, and 
ultimately to a confrontation with truths that would challenge everything they believed 
about themselves and their place in the world.
""",
        """
Chapter {chapter}: The Gathering Storm

Dark clouds gathered on the horizon as autumn gave way to winter, and with them came 
a sense of foreboding that settled over Thornwood like a heavy blanket. The harvest 
had been poor that year, and whispers of hardship to come passed from household to 
household, growing more dire with each retelling.

But it was not merely the weather or the economy that troubled the villagers. Strange 
occurrences had begun to plague the community - livestock found dead in their pens with 
no apparent cause, crops withering overnight despite careful tending, and most 
disturbingly, the disappearance of several travelers who had been passing through on 
their way to the city.

The authorities, such as they were in this remote corner of the kingdom, seemed either 
unable or unwilling to investigate these incidents with any seriousness. Some blamed 
bandits who were said to operate in the forests. Others spoke in hushed tones of older, 
darker forces that had awakened from long slumber.

Our protagonist, armed with the knowledge gleaned from their research in the library, 
began to suspect that these events were connected to the secret society mentioned in 
the old letter. If the organization still existed, could its members be responsible 
for the troubles afflicting Thornwood? Or were they, perhaps, the only ones capable 
of stopping whatever malevolent force had been unleashed?

The answers, when they came, would prove more complex and more terrifying than anyone 
could have anticipated.
""",
        """
Chapter {chapter}: Allies and Adversaries

In times of crisis, the true nature of people reveals itself. Some rise to meet the 
challenge, displaying courage and compassion that inspire others to follow their lead. 
Others succumb to fear and selfishness, willing to sacrifice anything and anyone to 
ensure their own survival.

Our hero found allies in unexpected places during those dark days. The blacksmith's 
daughter, whose sharp wit and sharper tongue had made her an outcast among the village 
girls, proved to be a loyal companion and a formidable fighter when circumstances 
demanded it. The elderly schoolmaster, dismissed by most as a harmless eccentric lost 
in his books, revealed a depth of knowledge about the occult that suggested a past far 
more adventurous than his current quiet existence would indicate.

But for every friend gained, an enemy emerged from the shadows. The wealthy merchant 
who had arrived with the railroad, his smile never quite reaching his cold eyes, seemed 
to take an unusual interest in our protagonist's investigations. The village priest, 
whose sermons had grown increasingly apocalyptic in recent weeks, watched their every 
move with barely concealed hostility.

Trust became a precious commodity, to be extended cautiously and withdrawn at the first 
sign of betrayal. In this atmosphere of suspicion and fear, our hero learned that the 
greatest battles are often fought not with swords or guns, but with words and wits, in 
the quiet moments between confrontations when alliances are forged and broken.

The path ahead was treacherous, but they were no longer walking it alone.
""",
        """
Chapter {chapter}: The Heart of Darkness

Every journey has its nadir, a point where hope seems lost and the temptation to 
surrender becomes almost overwhelming. For our protagonist, that moment came on a 
night when the moon hid its face behind clouds as black as pitch, and the wind 
howled through the streets of Thornwood like the voices of the damned.

They had followed the clues to their logical conclusion, only to find themselves 
trapped in a web of deceit far more intricate than they had imagined. The secret 
society was real, but its purpose was not what the old letter had suggested. What 
had begun as a noble endeavor to protect the innocent had been corrupted over the 
generations, twisted by greed and ambition until it had become the very evil it 
was created to oppose.

And at the center of this corruption stood a figure our hero had trusted implicitly, 
whose betrayal cut deeper than any physical wound could have. The revelation shattered 
not only their faith in others but their confidence in their own judgment. How could 
they hope to save Thornwood when they couldn't even recognize the enemy standing 
right beside them?

In that darkest hour, when despair threatened to consume them entirely, our protagonist 
found within themselves a spark of defiance that refused to be extinguished. They had 
come too far, sacrificed too much, to give up now. The people of Thornwood were counting 
on them, even if they didn't know it. And somewhere, in the depths of their soul, a 
voice whispered that this was the moment they had been born for.

The final confrontation was at hand.
"""
    ]
    
    paragraphs_needed = (target_tokens // 400) + 10
    sections = []
    
    for i in range(paragraphs_needed):
        template = story_templates[i % len(story_templates)]
        chapter = i + 1
        section = template.format(chapter=chapter)
        sections.append(section)
    
    return "\n".join(sections)


def generate_long_context_technical(target_tokens: int = 200000) -> str:
    """
    生成技术文档风格的超长上下文文本
    
    Args:
        target_tokens: 目标 token 数量（默认 200K）
    
    Returns:
        生成的长文本
    """
    # 技术文档风格的基础段落
    tech_templates = [
        """
## Section {section}: System Architecture Overview

### {section}.1 Introduction

This section provides a comprehensive overview of the system architecture, including 
the core components, their interactions, and the design principles that guide their 
implementation. Understanding this architecture is essential for developers who wish 
to extend or modify the system's functionality.

### {section}.2 Core Components

The system is built around several key components that work together to provide a 
robust and scalable solution:

1. **Request Handler**: Responsible for receiving and validating incoming requests 
   from clients. It performs initial authentication, rate limiting, and request 
   parsing before forwarding requests to the appropriate service.

2. **Service Layer**: Contains the business logic that processes requests and 
   generates responses. This layer is designed to be stateless, allowing for 
   horizontal scaling across multiple instances.

3. **Data Access Layer**: Manages all interactions with the underlying data stores, 
   including databases, caches, and external APIs. It implements connection pooling, 
   query optimization, and automatic retry logic for transient failures.

4. **Event Bus**: Facilitates asynchronous communication between components using 
   a publish-subscribe pattern. This enables loose coupling and allows components 
   to react to system events without direct dependencies.

### {section}.3 Design Principles

The architecture adheres to several key design principles:

- **Separation of Concerns**: Each component has a well-defined responsibility and 
  minimal knowledge of other components' internal workings.
- **Fail-Fast**: Components are designed to detect and report errors quickly, 
  preventing cascading failures throughout the system.
- **Graceful Degradation**: When individual components fail, the system continues 
  to operate with reduced functionality rather than failing completely.
""",
        """
## Section {section}: API Reference Documentation

### {section}.1 Authentication

All API requests must include a valid authentication token in the Authorization 
header. Tokens can be obtained through the OAuth 2.0 flow or by generating an 
API key through the developer console.

```
Authorization: Bearer <your-token-here>
```

Tokens expire after 24 hours and must be refreshed using the refresh token 
endpoint. Failed authentication attempts are logged and may result in temporary 
IP blocking after multiple failures.

### {section}.2 Rate Limiting

The API implements rate limiting to ensure fair usage and system stability. 
Default limits are:

| Tier       | Requests/minute | Requests/day |
|------------|-----------------|--------------|
| Free       | 60              | 1,000        |
| Standard   | 300             | 10,000       |
| Enterprise | 1,000           | Unlimited    |

When rate limits are exceeded, the API returns a 429 status code with a 
Retry-After header indicating when the client can retry.

### {section}.3 Error Handling

All errors are returned in a consistent JSON format:

```json
{{
  "error": {{
    "code": "INVALID_REQUEST",
    "message": "The request body is missing required field 'name'",
    "details": {{
      "field": "name",
      "constraint": "required"
    }}
  }}
}}
```

Common error codes include:
- `INVALID_REQUEST`: The request format is incorrect
- `UNAUTHORIZED`: Authentication failed or token expired
- `FORBIDDEN`: The authenticated user lacks permission
- `NOT_FOUND`: The requested resource does not exist
- `RATE_LIMITED`: Too many requests in the current time window
""",
        """
## Section {section}: Database Schema and Data Models

### {section}.1 Entity Relationship Overview

The system uses a relational database with the following primary entities:

**Users Table**
- `id` (UUID, Primary Key): Unique identifier for each user
- `email` (VARCHAR(255), Unique): User's email address
- `password_hash` (VARCHAR(255)): Bcrypt hash of the user's password
- `created_at` (TIMESTAMP): Account creation timestamp
- `updated_at` (TIMESTAMP): Last modification timestamp
- `status` (ENUM): Account status (active, suspended, deleted)

**Organizations Table**
- `id` (UUID, Primary Key): Unique identifier for each organization
- `name` (VARCHAR(255)): Organization display name
- `slug` (VARCHAR(100), Unique): URL-friendly identifier
- `owner_id` (UUID, Foreign Key): Reference to the owning user
- `settings` (JSONB): Organization-specific configuration

**Projects Table**
- `id` (UUID, Primary Key): Unique identifier for each project
- `organization_id` (UUID, Foreign Key): Parent organization
- `name` (VARCHAR(255)): Project display name
- `description` (TEXT): Detailed project description
- `visibility` (ENUM): Access level (private, internal, public)

### {section}.2 Indexing Strategy

To optimize query performance, the following indexes are maintained:

- Composite index on `(organization_id, created_at)` for listing projects
- Full-text index on `(name, description)` for search functionality
- Partial index on `status = 'active'` for filtering active records

### {section}.3 Data Migration Procedures

All schema changes must follow the migration protocol:

1. Create a new migration file with timestamp prefix
2. Implement both `up` and `down` methods
3. Test migration on staging environment
4. Schedule migration during maintenance window
5. Monitor system metrics during and after migration
""",
        """
## Section {section}: Performance Optimization Guidelines

### {section}.1 Caching Strategies

Effective caching is critical for system performance. The following caching 
layers are implemented:

**Application Cache (Redis)**
- Session data: TTL of 24 hours
- API responses: TTL varies by endpoint (1 minute to 1 hour)
- Computed values: TTL based on underlying data volatility

**CDN Cache (CloudFront)**
- Static assets: TTL of 1 year with cache-busting via content hash
- API responses: Selective caching for GET requests with appropriate headers

**Database Query Cache**
- Prepared statement caching for frequently executed queries
- Result set caching for expensive aggregation queries

### {section}.2 Query Optimization

Database queries should follow these optimization guidelines:

1. **Use EXPLAIN ANALYZE**: Always analyze query execution plans before 
   deploying new queries to production.

2. **Avoid N+1 Queries**: Use eager loading or batch fetching to minimize 
   database round trips.

3. **Limit Result Sets**: Always use pagination for queries that may return 
   large result sets. Default page size should be 20-50 items.

4. **Index Coverage**: Ensure frequently filtered and sorted columns are 
   properly indexed. Monitor slow query logs for optimization opportunities.

### {section}.3 Connection Pool Management

Database connections are managed through a connection pool with the following 
configuration:

- Minimum connections: 10
- Maximum connections: 100
- Connection timeout: 5 seconds
- Idle timeout: 300 seconds
- Max lifetime: 3600 seconds
""",
        """
## Section {section}: Security Best Practices

### {section}.1 Input Validation

All user input must be validated before processing:

**String Inputs**
- Maximum length enforcement
- Character whitelist/blacklist validation
- SQL injection prevention through parameterized queries
- XSS prevention through output encoding

**Numeric Inputs**
- Range validation (minimum/maximum values)
- Type coercion with explicit error handling
- Overflow protection for arithmetic operations

**File Uploads**
- File type validation via magic bytes, not just extension
- Maximum file size enforcement
- Virus scanning for uploaded files
- Secure storage with randomized filenames

### {section}.2 Authentication Security

The authentication system implements multiple security measures:

1. **Password Requirements**
   - Minimum 12 characters
   - Must include uppercase, lowercase, numbers, and symbols
   - Checked against common password databases
   - No reuse of last 10 passwords

2. **Multi-Factor Authentication**
   - TOTP-based authenticator app support
   - SMS backup codes (with security warnings)
   - Hardware security key support (WebAuthn)

3. **Session Management**
   - Secure, HttpOnly, SameSite cookies
   - Session invalidation on password change
   - Concurrent session limiting
   - Geographic anomaly detection

### {section}.3 Data Encryption

Sensitive data is protected through encryption:

- **At Rest**: AES-256 encryption for database fields containing PII
- **In Transit**: TLS 1.3 for all network communications
- **Key Management**: AWS KMS with automatic key rotation
"""
    ]
    
    paragraphs_needed = (target_tokens // 450) + 10
    sections = []
    
    for i in range(paragraphs_needed):
        template = tech_templates[i % len(tech_templates)]
        section_num = i + 1
        section = template.format(section=section_num)
        sections.append(section)
    
    return "\n".join(sections)


def test_long_context_with_cache():
    """
    测试超过 128K 长上下文 + 缓存功能
    
    这个测试验证：
    1. 模型能够处理超过 128K tokens 的长上下文
    2. 分段计费（tiered pricing）在长上下文场景下正确工作
    3. 缓存功能在长上下文场景下正常运行
    """
    print_separator("Test 5: Long Context (>128K) with Caching")
    
    print("Generating long context (~130K tokens)...")
    print("This may take a while...\n")
    
    # 生成超过 128K tokens 的长上下文
    long_context = generate_long_context(target_tokens=130000)
    
    # 估算 token 数量（粗略估计：1 token ≈ 4 字符）
    estimated_tokens = len(long_context) // 4
    print(f"Generated context length: {len(long_context):,} characters")
    print(f"Estimated tokens: ~{estimated_tokens:,} tokens")
    print(f"Target: >128,000 tokens (128K threshold for tiered pricing)\n")
    
    system_prompt = f"""You are a helpful AI assistant specialized in summarizing long documents.
You have been provided with an extensive document about AI and machine learning topics.
Please analyze the content carefully and provide concise, accurate responses.

=== DOCUMENT START ===
{long_context}
=== DOCUMENT END ===
"""
    
    print("Step 1: Creating initial response with long context and prefix caching enabled...")
    print("(This request will be slow due to the large context size)\n")
    
    start_time = time.time()
    
    # 第一次请求：启用前缀缓存
    response1 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Please provide a brief summary of the main topics covered in this document. List the top 5 themes."}
        ],
        caching={"type": "enabled", "prefix": True},
        thinking={"type": "disabled"},
        timeout=300  # 长上下文需要更长的超时时间
    )
    
    elapsed1 = time.time() - start_time
    
    if response1 is None:
        print("Error: Failed to create initial response")
        print("Note: This might be due to context length limits or timeout")
        return None, None
    
    print(f"Response 1 ID: {response1.id}")
    print(f"Time taken: {elapsed1:.2f} seconds")
    print("\nUsage (First Request - Full context processing):")
    print_usage(response1.usage)
    
    # 验证 token 数量是否超过 128K
    if response1.usage:
        input_tokens = response1.usage.input_tokens
        print(f"\n[INFO] Actual input tokens: {input_tokens:,}")
        if input_tokens > 128000:
            print(f"[OK] Context exceeds 128K threshold! Tiered pricing should apply.")
        else:
            print(f"[WARN] Context is below 128K threshold ({input_tokens:,} < 128,000)")
    
    text = get_output_text(response1)
    if text:
        print(f"\nOutput:\n{text[:500]}...")
    
    # 等待缓存创建 - 长上下文需要更长的缓存创建时间
    print("\nWaiting for cache to be created (30 seconds for long context)...")
    time.sleep(30)
    
    # 第二次请求：使用 previous_response_id 利用缓存
    print("\nStep 2: Using previous_response_id to leverage cache...")
    print("(This request should be much faster due to cache hit)\n")
    
    start_time = time.time()
    
    response2 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "Based on the document, what are the key challenges mentioned in AI research?"}
        ],
        previous_response_id=response1.id,
        caching={"type": "enabled"},
        thinking={"type": "disabled"},
        timeout=300
    )
    
    elapsed2 = time.time() - start_time
    
    if response2 is None:
        print("Error: Failed to create second response")
        return response1, None
    
    print(f"Response 2 ID: {response2.id}")
    print(f"Time taken: {elapsed2:.2f} seconds")
    print(f"Speed improvement: {elapsed1/elapsed2:.1f}x faster" if elapsed2 > 0 else "")
    print("\nUsage (Second Request - Should show cached tokens):")
    print_usage(response2.usage)
    
    text2 = get_output_text(response2)
    if text2:
        print(f"\nOutput:\n{text2[:500]}...")
    
    # 检查缓存命中
    if response2.usage and response2.usage.input_tokens_details:
        cached = response2.usage.input_tokens_details.cached_tokens
        total_input = response2.usage.input_tokens
        if cached > 0:
            cache_ratio = (cached / total_input * 100) if total_input > 0 else 0
            print(f"\n[OK] Cache HIT!")
            print(f"  - Cached tokens: {cached:,}")
            print(f"  - Total input tokens: {total_input:,}")
            print(f"  - Cache hit ratio: {cache_ratio:.1f}%")
            
            if cached > 128000:
                print(f"  - [OK] Cached tokens exceed 128K - tiered pricing applies to cached portion")
        else:
            print("\n[WARN] No cache hit detected (cached_tokens = 0)")
            print("  This might be due to:")
            print("  - Cache not yet created (try increasing wait time)")
            print("  - Cache eviction due to memory pressure")
            print("  - Model/provider limitations")
    
    # 第三次请求：继续对话，验证缓存持续有效
    print("\nStep 3: Third request to verify cache persistence...")
    
    start_time = time.time()
    
    response3 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "What solutions or approaches are suggested in the document to address these challenges?"}
        ],
        previous_response_id=response2.id,
        caching={"type": "enabled"},
        thinking={"type": "disabled"},
        timeout=300
    )
    
    elapsed3 = time.time() - start_time
    
    if response3:
        print(f"Response 3 ID: {response3.id}")
        print(f"Time taken: {elapsed3:.2f} seconds")
        print("\nUsage (Third Request):")
        print_usage(response3.usage)
        
        if response3.usage and response3.usage.input_tokens_details:
            cached = response3.usage.input_tokens_details.cached_tokens
            if cached > 0:
                print(f"\n[OK] Cache still active! Cached tokens: {cached:,}")
    
    return response1, response2


def test_long_context_literature():
    """
    测试文学风格的超长上下文 + 缓存功能
    
    使用小说/故事风格的文本，测试 200K+ tokens 场景
    """
    print_separator("Test 6: Literature Style Long Context (~200K)")
    
    print("Generating literature-style long context (~200K tokens)...")
    print("This may take a while...\n")
    
    # 生成约 200K tokens 的文学风格文本
    long_context = generate_long_context_literature(target_tokens=200000)
    
    estimated_tokens = len(long_context) // 4
    print(f"Generated context length: {len(long_context):,} characters")
    print(f"Estimated tokens: ~{estimated_tokens:,} tokens")
    print(f"Target: ~200,000 tokens (128-256K tier)\n")
    
    system_prompt = f"""You are a literary critic and story analyst. You have been provided with 
an extensive novel manuscript. Please analyze the content carefully and provide insightful responses.

=== MANUSCRIPT START ===
{long_context}
=== MANUSCRIPT END ===
"""
    
    print("Step 1: Creating initial response with literature context...")
    start_time = time.time()
    
    response1 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Analyze the narrative structure of this story. What are the main plot points and how do they connect?"}
        ],
        caching={"type": "enabled", "prefix": True},
        thinking={"type": "disabled"},
        timeout=600
    )
    
    elapsed1 = time.time() - start_time
    
    if response1 is None:
        print("Error: Failed to create initial response")
        return None, None
    
    print(f"Response 1 ID: {response1.id}")
    print(f"Time taken: {elapsed1:.2f} seconds")
    print("\nUsage (First Request):")
    print_usage(response1.usage)
    
    if response1.usage:
        input_tokens = response1.usage.input_tokens
        print(f"\n[INFO] Actual input tokens: {input_tokens:,}")
        if input_tokens > 128000:
            print(f"[OK] Context in 128-256K tier!")
        if input_tokens > 256000:
            print(f"[OK] Context exceeds 256K!")
    
    text = get_output_text(response1)
    if text:
        print(f"\nOutput:\n{text[:400]}...")
    
    print("\nWaiting for cache to be created (30 seconds)...")
    time.sleep(30)
    
    print("\nStep 2: Using cache for follow-up question...")
    start_time = time.time()
    
    response2 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "Who is the protagonist and what motivates them throughout the story?"}
        ],
        previous_response_id=response1.id,
        caching={"type": "enabled"},
        thinking={"type": "disabled"},
        timeout=600
    )
    
    elapsed2 = time.time() - start_time
    
    if response2 is None:
        print("Error: Failed to create second response")
        return response1, None
    
    print(f"Response 2 ID: {response2.id}")
    print(f"Time taken: {elapsed2:.2f} seconds")
    print(f"Speed improvement: {elapsed1/elapsed2:.1f}x faster" if elapsed2 > 0 else "")
    print("\nUsage (Second Request - Should show cached tokens):")
    print_usage(response2.usage)
    
    if response2.usage and response2.usage.input_tokens_details:
        cached = response2.usage.input_tokens_details.cached_tokens
        if cached > 0:
            print(f"\n[OK] Cache HIT! Cached tokens: {cached:,}")
        else:
            print("\n[WARN] No cache hit detected")
    
    return response1, response2


def test_long_context_technical():
    """
    测试技术文档风格的超长上下文 + 缓存功能
    
    使用 API 文档/技术规范风格的文本，测试 200K+ tokens 场景
    """
    print_separator("Test 7: Technical Documentation Long Context (~200K)")
    
    print("Generating technical documentation (~200K tokens)...")
    print("This may take a while...\n")
    
    # 生成约 200K tokens 的技术文档风格文本
    long_context = generate_long_context_technical(target_tokens=200000)
    
    estimated_tokens = len(long_context) // 4
    print(f"Generated context length: {len(long_context):,} characters")
    print(f"Estimated tokens: ~{estimated_tokens:,} tokens")
    print(f"Target: ~200,000 tokens (128-256K tier)\n")
    
    system_prompt = f"""You are a senior software architect reviewing technical documentation.
You have been provided with comprehensive system documentation. Please analyze it and provide 
expert-level responses.

=== DOCUMENTATION START ===
{long_context}
=== DOCUMENTATION END ===
"""
    
    print("Step 1: Creating initial response with technical documentation...")
    start_time = time.time()
    
    response1 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Summarize the key architectural decisions described in this documentation. What are the main design patterns used?"}
        ],
        caching={"type": "enabled", "prefix": True},
        thinking={"type": "disabled"},
        timeout=600
    )
    
    elapsed1 = time.time() - start_time
    
    if response1 is None:
        print("Error: Failed to create initial response")
        return None, None
    
    print(f"Response 1 ID: {response1.id}")
    print(f"Time taken: {elapsed1:.2f} seconds")
    print("\nUsage (First Request):")
    print_usage(response1.usage)
    
    if response1.usage:
        input_tokens = response1.usage.input_tokens
        print(f"\n[INFO] Actual input tokens: {input_tokens:,}")
        if input_tokens > 128000:
            print(f"[OK] Context in 128-256K tier!")
        if input_tokens > 256000:
            print(f"[OK] Context exceeds 256K!")
    
    text = get_output_text(response1)
    if text:
        print(f"\nOutput:\n{text[:400]}...")
    
    print("\nWaiting for cache to be created (30 seconds)...")
    time.sleep(30)
    
    print("\nStep 2: Using cache for follow-up question...")
    start_time = time.time()
    
    response2 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "What security measures are described in the documentation? List the key security features."}
        ],
        previous_response_id=response1.id,
        caching={"type": "enabled"},
        thinking={"type": "disabled"},
        timeout=600
    )
    
    elapsed2 = time.time() - start_time
    
    if response2 is None:
        print("Error: Failed to create second response")
        return response1, None
    
    print(f"Response 2 ID: {response2.id}")
    print(f"Time taken: {elapsed2:.2f} seconds")
    print(f"Speed improvement: {elapsed1/elapsed2:.1f}x faster" if elapsed2 > 0 else "")
    print("\nUsage (Second Request - Should show cached tokens):")
    print_usage(response2.usage)
    
    if response2.usage and response2.usage.input_tokens_details:
        cached = response2.usage.input_tokens_details.cached_tokens
        if cached > 0:
            print(f"\n[OK] Cache HIT! Cached tokens: {cached:,}")
        else:
            print("\n[WARN] No cache hit detected")
    
    return response1, response2


def main():
    """主测试函数"""
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║     BytePlus Responses API Cache Test Suite                  ║
╠══════════════════════════════════════════════════════════════╣
║  Base URL: {BASE_URL:<48} ║
║  Model:    {MODEL:<48} ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    results = {}
    
    # Test 1: Basic Responses API
    response1 = test_basic_responses()
    results['basic'] = response1 is not None
    
    # Test 2: Prefix Caching
    r1, r2 = test_prefix_caching()
    results['prefix_caching'] = r1 is not None and r2 is not None
    
    # Test 3: Thinking Mode
    response3 = test_thinking_mode()
    results['thinking_mode'] = response3 is not None
    
    # Test 4: Streaming
    results['streaming'] = test_streaming()
    
    # Test 5: Long Context (>128K) with Caching
    # 注意：这个测试需要较长时间，可以单独运行
    print("\n" + "="*60)
    print("  Note: Test 5 (Long Context >128K) is optional and slow.")
    print("  To run it separately: python test_byteplus_responses_cache.py --long-context")
    print("="*60)
    
    # Summary
    print_separator("Test Summary")
    for test_name, passed in results.items():
        status = "[PASSED]" if passed else "[FAILED]"
        print(f"  {test_name}: {status}")
    
    total_passed = sum(results.values())
    total_tests = len(results)
    print(f"\n  Total: {total_passed}/{total_tests} tests passed")


def main_long_context():
    """单独运行所有长上下文测试"""
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║     BytePlus Long Context (>128K) Cache Test Suite           ║
╠══════════════════════════════════════════════════════════════╣
║  Base URL: {BASE_URL:<48} ║
║  Model:    {MODEL:<48} ║
║                                                              ║
║  This test suite validates:                                  ║
║  - Long context processing (>128K tokens)                    ║
║  - Tiered pricing for extended context                       ║
║  - Cache functionality with large context                    ║
║                                                              ║
║  Tests included:                                             ║
║  - Test 5: AI/ML Content (~130K tokens)                      ║
║  - Test 6: Literature Style (~200K tokens)                   ║
║  - Test 7: Technical Documentation (~200K tokens)            ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    results = {}
    
    # Test 5: AI/ML 风格长上下文 (~130K)
    print("\n" + "="*70)
    print("  Running Test 5: AI/ML Content Long Context (~130K tokens)")
    print("="*70)
    r1, r2 = test_long_context_with_cache()
    results['ai_ml_130k'] = {
        'passed': r1 is not None and r2 is not None,
        'input_tokens': r1.usage.input_tokens if r1 and r1.usage else 0,
        'cached_tokens': r2.usage.input_tokens_details.cached_tokens if r2 and r2.usage and r2.usage.input_tokens_details else 0
    }
    
    # Test 6: 文学风格长上下文 (~200K)
    print("\n" + "="*70)
    print("  Running Test 6: Literature Style Long Context (~200K tokens)")
    print("="*70)
    r3, r4 = test_long_context_literature()
    results['literature_200k'] = {
        'passed': r3 is not None and r4 is not None,
        'input_tokens': r3.usage.input_tokens if r3 and r3.usage else 0,
        'cached_tokens': r4.usage.input_tokens_details.cached_tokens if r4 and r4.usage and r4.usage.input_tokens_details else 0
    }
    
    # Test 7: 技术文档风格长上下文 (~200K)
    print("\n" + "="*70)
    print("  Running Test 7: Technical Documentation Long Context (~200K tokens)")
    print("="*70)
    r5, r6 = test_long_context_technical()
    results['technical_200k'] = {
        'passed': r5 is not None and r6 is not None,
        'input_tokens': r5.usage.input_tokens if r5 and r5.usage else 0,
        'cached_tokens': r6.usage.input_tokens_details.cached_tokens if r6 and r6.usage and r6.usage.input_tokens_details else 0
    }
    
    # 打印汇总结果
    print_separator("Long Context Test Suite Summary")
    
    print("┌─────────────────────────────┬──────────┬───────────────┬───────────────┐")
    print("│ Test                        │ Status   │ Input Tokens  │ Cached Tokens │")
    print("├─────────────────────────────┼──────────┼───────────────┼───────────────┤")
    
    for test_name, result in results.items():
        status = "[PASS]" if result['passed'] else "[FAIL]"
        input_tokens = f"{result['input_tokens']:,}" if result['input_tokens'] > 0 else "N/A"
        cached_tokens = f"{result['cached_tokens']:,}" if result['cached_tokens'] > 0 else "0"
        print(f"│ {test_name:<27} │ {status:<8} │ {input_tokens:>13} │ {cached_tokens:>13} │")
    
    print("└─────────────────────────────┴──────────┴───────────────┴───────────────┘")
    
    # 统计
    total_passed = sum(1 for r in results.values() if r['passed'])
    total_tests = len(results)
    total_input_tokens = sum(r['input_tokens'] for r in results.values())
    total_cached_tokens = sum(r['cached_tokens'] for r in results.values())
    
    print(f"\n  Total: {total_passed}/{total_tests} tests passed")
    print(f"  Total input tokens processed: {total_input_tokens:,}")
    print(f"  Total cached tokens: {total_cached_tokens:,}")
    
    if total_cached_tokens > 0:
        print(f"\n  [OK] Caching is working! Cache efficiency demonstrated.")
    else:
        print(f"\n  [WARN] No cache hits detected across all tests.")
        print("  Consider increasing wait time between requests or check provider settings.")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--long-context":
        main_long_context()
    else:
        main()

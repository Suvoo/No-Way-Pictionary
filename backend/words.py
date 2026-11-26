"""Word bank for Reverse Pictionary.

Plain data, no game logic. To add a word:
  1. add an entry to WORDS below (variants = other answers that count as correct),
  2. add a stroke template with the same key to strokes.json,
  3. run `python backend/evals/run_evals.py` (it checks every word has strokes).

Source: Google Quick, Draw! categories (CC BY 4.0),
https://github.com/googlecreativelab/quickdraw-dataset . V1 uses a curated easy subset:
simple nouns, one clear object, big shape. No verbs, adjectives or abstract ideas.
"""
from __future__ import annotations

from typing import Dict, List, TypedDict


class WordEntry(TypedDict):
    variants: List[str]  # other spellings / synonyms accepted as a correct guess
    hint: str  # one line, shown after 2 wrong guesses (PAL-draw rounds only)
    quickdraw: str  # the Quick Draw category this word comes from


WORDS: Dict[str, WordEntry] = {
    "star": {"variants": ["stars"], "hint": "It twinkles in the night sky.", "quickdraw": "star"},
    "sun": {"variants": ["sunshine"], "hint": "It is hot and bright and up in the sky.", "quickdraw": "sun"},
    "house": {"variants": ["home", "hut", "cottage", "cabin"], "hint": "You live in one.", "quickdraw": "house"},
    "heart": {"variants": ["love heart"], "hint": "It means love.", "quickdraw": "(not in Quick Draw, added by hand)"},
    "fish": {"variants": ["goldfish"], "hint": "It swims.", "quickdraw": "fish"},
    "tree": {"variants": ["trees"], "hint": "It grows leaves.", "quickdraw": "tree"},
    "car": {"variants": ["automobile", "taxi"], "hint": "You drive it.", "quickdraw": "car"},
    "cat": {"variants": ["kitty", "kitten", "cat face"], "hint": "It says meow.", "quickdraw": "cat"},
    "smiley face": {"variants": ["smiley", "happy face", "smile face", "smiling face", "emoji"], "hint": "It is a happy face.", "quickdraw": "smiley face"},
    "glasses": {"variants": ["eyeglasses", "spectacles", "specs", "sunglasses"], "hint": "You wear them to see better.", "quickdraw": "eyeglasses"},
    "cup": {"variants": ["mug", "teacup", "coffee cup", "tea cup"], "hint": "You drink from it.", "quickdraw": "cup"},
    "key": {"variants": ["keys"], "hint": "It opens a door.", "quickdraw": "key"},
    "umbrella": {"variants": ["parasol", "brolly"], "hint": "It keeps you dry in the rain.", "quickdraw": "umbrella"},
    "boat": {"variants": ["sailboat", "sail boat", "ship", "sailing boat", "yacht"], "hint": "It floats on water.", "quickdraw": "sailboat"},
    "bird": {"variants": ["birdie", "chick"], "hint": "It flies and tweets.", "quickdraw": "bird"},
    "chair": {"variants": ["seat"], "hint": "You sit on it.", "quickdraw": "chair"},
    "clock": {"variants": ["wall clock", "watch"], "hint": "It tells the time.", "quickdraw": "clock"},
    "flower": {"variants": ["daisy", "sunflower", "tulip", "rose"], "hint": "It grows in a garden and smells nice.", "quickdraw": "flower"},
    "moon": {"variants": ["crescent", "crescent moon", "half moon"], "hint": "You see it at night.", "quickdraw": "moon"},
    "bicycle": {"variants": ["bike", "cycle", "push bike"], "hint": "It has two wheels and you ride it.", "quickdraw": "bicycle"},
    "apple": {"variants": ["apples"], "hint": "A fruit that keeps the doctor away.", "quickdraw": "apple"},
    "envelope": {"variants": ["letter", "mail"], "hint": "You post a letter in it.", "quickdraw": "envelope"},
    "snowman": {"variants": ["snow man", "snowmen"], "hint": "You build it in winter.", "quickdraw": "snowman"},
    "balloon": {"variants": ["balloons", "hot air balloon"], "hint": "It floats away at a birthday party.", "quickdraw": "hot air balloon"},
    "mushroom": {"variants": ["toadstool"], "hint": "It grows in a forest and has a cap.", "quickdraw": "mushroom"},
    "ladder": {"variants": ["step ladder"], "hint": "You climb it.", "quickdraw": "ladder"},
    "ice cream": {"variants": ["icecream", "ice cream cone", "ice-cream"], "hint": "A cold sweet treat in a cone.", "quickdraw": "ice cream"},
    "pizza": {"variants": ["pizza slice", "slice of pizza"], "hint": "A cheesy food from Italy.", "quickdraw": "pizza"},
}

V1_WORDS: List[str] = list(WORDS.keys())

# Words deliberately excluded from v1: too hard to draw in 45 seconds or for Raven to read.
EXCLUDED_EXAMPLES: List[str] = ["aircraft carrier", "The Eiffel Tower", "The Mona Lisa", "yoga", "camouflage"]

# Full Quick Draw category list (345), kept as reference for expanding the word bank later.
QUICKDRAW_CATEGORIES: List[str] = [
    'aircraft carrier', 'airplane', 'alarm clock', 'ambulance', 'angel', 'animal migration',
    'ant', 'anvil', 'apple', 'arm', 'asparagus', 'axe', 'backpack', 'banana', 'bandage',
    'barn', 'baseball', 'baseball bat', 'basket', 'basketball', 'bat', 'bathtub', 'beach',
    'bear', 'beard', 'bed', 'bee', 'belt', 'bench', 'bicycle', 'binoculars', 'bird',
    'birthday cake', 'blackberry', 'blueberry', 'book', 'boomerang', 'bottlecap', 'bowtie',
    'bracelet', 'brain', 'bread', 'bridge', 'broccoli', 'broom', 'bucket', 'bulldozer',
    'bus', 'bush', 'butterfly', 'cactus', 'cake', 'calculator', 'calendar', 'camel',
    'camera', 'camouflage', 'campfire', 'candle', 'cannon', 'canoe', 'car', 'carrot',
    'castle', 'cat', 'ceiling fan', 'cello', 'cell phone', 'chair', 'chandelier', 'church',
    'circle', 'clarinet', 'clock', 'cloud', 'coffee cup', 'compass', 'computer', 'cookie',
    'cooler', 'couch', 'cow', 'crab', 'crayon', 'crocodile', 'crown', 'cruise ship', 'cup',
    'diamond', 'dishwasher', 'diving board', 'dog', 'dolphin', 'donut', 'door', 'dragon',
    'dresser', 'drill', 'drums', 'duck', 'dumbbell', 'ear', 'elbow', 'elephant', 'envelope',
    'eraser', 'eye', 'eyeglasses', 'face', 'fan', 'feather', 'fence', 'finger',
    'fire hydrant', 'fireplace', 'firetruck', 'fish', 'flamingo', 'flashlight',
    'flip flops', 'floor lamp', 'flower', 'flying saucer', 'foot', 'fork', 'frog',
    'frying pan', 'garden', 'garden hose', 'giraffe', 'goatee', 'golf club', 'grapes',
    'grass', 'guitar', 'hamburger', 'hammer', 'hand', 'harp', 'hat', 'headphones',
    'hedgehog', 'helicopter', 'helmet', 'hexagon', 'hockey puck', 'hockey stick', 'horse',
    'hospital', 'hot air balloon', 'hot dog', 'hot tub', 'hourglass', 'house',
    'house plant', 'hurricane', 'ice cream', 'jacket', 'jail', 'kangaroo', 'key',
    'keyboard', 'knee', 'knife', 'ladder', 'lantern', 'laptop', 'leaf', 'leg', 'light bulb',
    'lighter', 'lighthouse', 'lightning', 'line', 'lion', 'lipstick', 'lobster', 'lollipop',
    'mailbox', 'map', 'marker', 'matches', 'megaphone', 'mermaid', 'microphone',
    'microwave', 'monkey', 'moon', 'mosquito', 'motorbike', 'mountain', 'mouse',
    'moustache', 'mouth', 'mug', 'mushroom', 'nail', 'necklace', 'nose', 'ocean', 'octagon',
    'octopus', 'onion', 'oven', 'owl', 'paintbrush', 'paint can', 'palm tree', 'panda',
    'pants', 'paper clip', 'parachute', 'parrot', 'passport', 'peanut', 'pear', 'peas',
    'pencil', 'penguin', 'piano', 'pickup truck', 'picture frame', 'pig', 'pillow',
    'pineapple', 'pizza', 'pliers', 'police car', 'pond', 'pool', 'popsicle', 'postcard',
    'potato', 'power outlet', 'purse', 'rabbit', 'raccoon', 'radio', 'rain', 'rainbow',
    'rake', 'remote control', 'rhinoceros', 'rifle', 'river', 'roller coaster',
    'rollerskates', 'sailboat', 'sandwich', 'saw', 'saxophone', 'school bus', 'scissors',
    'scorpion', 'screwdriver', 'sea turtle', 'see saw', 'shark', 'sheep', 'shoe', 'shorts',
    'shovel', 'sink', 'skateboard', 'skull', 'skyscraper', 'sleeping bag', 'smiley face',
    'snail', 'snake', 'snorkel', 'snowflake', 'snowman', 'soccer ball', 'sock', 'speedboat',
    'spider', 'spoon', 'spreadsheet', 'square', 'squiggle', 'squirrel', 'stairs', 'star',
    'steak', 'stereo', 'stethoscope', 'stitches', 'stop sign', 'stove', 'strawberry',
    'streetlight', 'string bean', 'submarine', 'suitcase', 'sun', 'swan', 'sweater',
    'swing set', 'sword', 'syringe', 'table', 'teapot', 'teddy-bear', 'telephone',
    'television', 'tennis racquet', 'tent', 'The Eiffel Tower', 'The Great Wall of China',
    'The Mona Lisa', 'tiger', 'toaster', 'toe', 'toilet', 'tooth', 'toothbrush',
    'toothpaste', 'tornado', 'tractor', 'traffic light', 'train', 'tree', 'triangle',
    'trombone', 'truck', 'trumpet', 't-shirt', 'umbrella', 'underwear', 'van', 'vase',
    'violin', 'washing machine', 'watermelon', 'waterslide', 'whale', 'wheel', 'windmill',
    'wine bottle', 'wine glass', 'wristwatch', 'yoga', 'zebra', 'zigzag',
]

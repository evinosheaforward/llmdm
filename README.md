# README

## Work In Progress

This project is certainly nowhere near done. What I have is:
 - Basic game REPL where you have options based on what game state you're in (free or conversation)
 - Actions you can take such as travel, retrieving game data (this is to help with the work in progress nature of the state of things), and starting conversations
 - When a new game starts, the game generates a starting town with some locations and NPCs
 - You can travel between locations including going from "in the town" to sublocations like "the tavern" and vice-versa.
 - You can start conversations with NPCs. You can also ask to talk to "the barkeep" and if they are not already there, one will be generated.
 - NPCs have character traits and affinity scores for players.
 - When you talk to an NPC, they have a motivation for the conversation and they may give you a quest. When a conversation concludes, the NPC's affinity score toward you can change. The affinity scores have "levels" such as enemy, friendly, ally, etc.
 - Conversations are summarized and saved so when you talk to the NPC again, they will "remember" the previous conversation.

What I'd like to add next are:
 - Add detail to locations - i.e. rooms to a building or other spatial relationships between locations.
 - Continue to expand story data so that NPCs can learn about events that happen that aren't conversations with them directly.
 - Add validation to action inputs so if you say you want to speak to the king and that would be impossible, the game would tell you no.
 - Continue to improve story data adding more events that are saved to the vector database.
 - Continue to improve story data by leveraging the graph database for retrieving information about other aspects of the story when necessary. NPC actions are currently too isolated.
 - Add validation to the internals of the game so that responses are "fact-checked" for validity and uniqueness.
 - Improve the creativity/variety of the outputs of the LLM when generating pieces of the story (NPCs, locations, quests). The LLM doesn't need to do something that's never been done before, but it also can't create the same 5 NPCs over and over.


Long term, I'd want to add a combat system, character abilities, and character progression. I'd approach that through:
 - Adding a first class like fighter, adding an attack mechanic.
 - Adding a combat game state where the actions are to use character abilites or run. The ability to "attack", "diffuse" the fight, or "intimidate" the enemy into surrender would all be class abilites.
 - Add a system for enemies, their abilities and how they use them. Start with a goblin that has 1 attack per round.
 - Add health and damage for the player.
 - Add system for initiating combat by enemies and the player.
 - Add system for ending combat.


The last piece of work for the game would be a constant persuit of improving the way pieces of the story are generated, stored, and validated.

I have found that there are limitations to LLMs that make what this game tries to do difficult:
 - The quality of the model matters - the small llama 3.x models are great for working on the game since if a prompt works for them, it will work for, i.e. GPT-4o.
 - The way data is stored and retrieved matters a lot. The context supplied to a prompt has to be carefully selected to make sure the resonse is valid, and that the context is leveraged (too much context, of course, causes things to be missed).
 - It is interesting how, once the goal of the game is to use the LLM beyond a single "conversation" (i.e. context window) then the task of storing and retrieving data becomes very complex.
 - The LLMs are not creative. Human creativity needs to be injected to make the LLM creative. I would like to expand the game to let the player come up with ideas - for example create a concept for a city and the culture and have the LLM use that input to create unique characters. Otherwise, re-using similar prompts will result in similar NPCs and locations over and over. For now I have addressed this a little bit by having large pre-generated lists of types and names for NPCs and locations, but there is a lot of room for improvement there. This is by far the hardest part of the project.

What I have learned works well is:
 - Breaking down the tasks into smaller chunks is essential to making tasks the LLMS can complete.
 - Focusing on the data modeling and the traditional coding aspects of the game come first.
 - Prompting the LLM with the relevant data. When the prompt has all the data it needs, it typically outputs interesting results (at this stage, that is mainly NPC conversations).

## Requirements:

python3, cuda (if using HuggingFace models), podman (can use docker with alias podman="docker")

The python requirements will be installed when you build the env or install the python package.


## Setup

You will need to set your `HF_TOKEN` to use the default (LLAMA3 model, which you need permission from Meta to use), or use model that is open on Hugging Face by setting `LLMDM_MODEL`

You can also use OpenAI's API if you set `USE_OPENAI=true` and set the `OPENAI_API_KEY` environment variable with your api key.

## To install the game globally and run it you can run:
```
s/install
s/db_up
llmdm
```

Or to setup the project to run the game, you can run:
```
poetry install
poetry run llmdm
```

Logs go to `/tmp/llmdm.log`.
You can also run in debug mode to print logs to standard out with:
```
poetry run lldm-debug
```


## To reset the dbs / clear saves, run
```
s/reset
```

## Opensearch dashboard

In case you want to look through the opensearch data, you can do `s/run_opensearch_dashboard.sh`
and connect to it in your browser at localhost:5601.

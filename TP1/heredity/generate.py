"""
Make a simple random family tree CSV

Usage:
     generate.py                    
     generate.py --generations 3
     generate.py --children 4 --unknown 0.5 --seed 7
"""

import argparse
import csv
import os
import random

NAMES = ["Ana", "Rui", "Sofia", "Tiago", "Ines", "Pedro", "Rita", "Joao",
         "Marta", "Luis", "Carla", "Nuno", "Beatriz", "Miguel", "Joana", "Diogo"]

DATA_FOLDER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def make_family(generations, max_children, max_people, rng):
    """Return a list of [name, mother, father], at most max_people long."""
    names = rng.sample(NAMES, len(NAMES))        # shuffled, so no repeats
    mother, father = names.pop(), names.pop()
    people = [[mother, "", ""], [father, "", ""]]

    # With 3 generations
    limit = max_people - 2 if generations >= 3 else max_people

    kids = []
    for _ in range(rng.randint(1, max_children)):
        if len(people) >= limit:
            break
        kid = names.pop()
        people.append([kid, mother, father])
        kids.append(kid)

    if generations >= 3:
        parent = rng.choice(kids)
        partner = names.pop()
        people.append([partner, "", ""])
        for _ in range(rng.randint(1, max_children)):
            if len(people) >= max_people:
                break
            # we don't track sex, so just pick who is "mother"
            people.append([names.pop(), parent, partner])

    return people


def random_trait(unknown, rng):
    """Empty = unknown, otherwise 1 (has trait, rarer) or 0."""
    if rng.random() < unknown:
        return ""
    return "1" if rng.random() < 0.25 else "0"


def next_filename():
    """data/family3.csv, data/family4.csv, ... the first one that doesn't exist."""
    n = 0
    while os.path.exists(os.path.join(DATA_FOLDER_PATH, f"family{n}.csv")):
        n += 1
    return os.path.join(DATA_FOLDER_PATH, f"family{n}.csv")


def main():
    parser = argparse.ArgumentParser(description="Generate a simple family CSV")
    parser.add_argument("--generations", type=int, choices=[2, 3], default=2)
    parser.add_argument("--children", type=int, default=3,
                        help="max kids per couple (default 3)")
    parser.add_argument("--unknown", type=float, default=0.4,
                        help="chance a trait is left empty (default 0.4)")
    parser.add_argument("--max-people", type=int, default=8,
                        help="never more than this many (default 8, the app's limit)")
    parser.add_argument("--seed", type=int, help="same seed = same family")
    args = parser.parse_args()
    if args.max_people < 3 or (args.generations == 3 and args.max_people < 5):
        parser.error("--max-people is too small for that many generations")

    rng = random.Random(args.seed)
    people = make_family(args.generations, args.children, args.max_people, rng)

    os.makedirs(DATA_FOLDER_PATH, exist_ok=True)
    filename = next_filename()
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "mother", "father", "trait"])
        for name, mother, father in people:
            writer.writerow([name, mother, father, random_trait(args.unknown, rng)])

    print(f"Saved {len(people)} people to {filename}")
    if len(people) > 8:
        print("Note: app.py only handles up to 8 people. Try fewer --children.")


if __name__ == "__main__":
    main()
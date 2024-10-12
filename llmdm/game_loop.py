def main():
    game = load_game()
    while True:
        game.prompt()
        game.validate()
        game.respond()
        game.update_state()


if __name__ == "__main__":
    main()

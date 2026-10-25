from getpass import getpass

from app import create_initial_superadmin


def main():
    print("Create the first BidMart Superadmin (local setup only).")
    print("If this email already belongs to a verified User, enter that account's current password to upgrade it.")
    full_name = input("Full name: ")
    email = input("Email: ")
    password = getpass("Existing account password, or new password (at least 8 characters): ")

    try:
        result = create_initial_superadmin(full_name, email, password)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    except Exception as error:
        if "UNIQUE constraint failed: accounts.email" in str(error):
            raise SystemExit(
                "An account with that email already exists. Use its current password to upgrade it."
            ) from error
        raise SystemExit(f"Could not create the initial Superadmin: {error}") from error
    if result == "upgraded":
        print("Existing User account upgraded to the initial Superadmin.")
    else:
        print("Initial Superadmin created. Sign in with this email and password.")


if __name__ == "__main__":
    main()

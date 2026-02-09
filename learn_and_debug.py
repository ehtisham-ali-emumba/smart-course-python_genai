# Demonstrates exception handling in Python
def demonstrate_exception_handling() -> None:
    try:
        # Try to convert input to integer
        int("not_a_number")
    except ValueError as e:
        print("Caught a ValueError:", e)
        # Raising a new exception
        raise RuntimeError("Something went wrong with conversion!") from e
    finally:
        print("This block always runs (cleanup, closing files, etc.)")

    # Example with no exception
    try:
        result: float = 10 / 2
        print("Result:", result)
    except ZeroDivisionError:
        print("Cannot divide by zero!")
    finally:
        print("Finished division example.")


# Demonstrates the four OOP principles in Python
def demonstrate_oop_principles() -> None:
    # 1. Encapsulation: Bundling data and methods
    class Animal:
        def __init__(self, name: str) -> None:
            self._name = name  # _name is encapsulated (protected)

        def speak(self) -> None:
            print(f"{self._name} makes a sound.")

    # 2. Inheritance: Child class inherits from parent
    class Dog(Animal):
        def speak(self) -> None:
            print(f"{self._name} barks.")

    # 3. Polymorphism: Same method, different behavior
    class Cat(Animal):
        def speak(self) -> None:
            print(f"{self._name} meows.")

    # 4. Abstraction: Using abstract base class
    from abc import ABC, abstractmethod

    class Shape(ABC):
        @abstractmethod
        def area(self) -> float:
            pass

    class Rectangle(Shape):
        def __init__(self, width: float, height: float) -> None:
            self.width = width
            self.height = height

        def area(self) -> float:
            return self.width * self.height

    # Demonstrate encapsulation
    animal = Animal("Generic Animal")
    animal.speak()

    # Demonstrate abstraction
    rect = Rectangle(3, 4)
    print(f"Rectangle area: {rect.area()}")

    car = Cat("Whiskers")
    dog = Dog("Rex")
    print("\nDemonstrating polymorphism:")
    for pet in (car, dog):
        pet.speak()


# Demonstrates how to define and use classes in Python
def demonstrate_classes() -> None:
    # Define a simple class
    class Student:
        # Constructor (initializer)
        def __init__(self, name: str, age: int) -> None:
            self.name = name  # Instance variable
            self.age = age

        # Method
        def greet(self) -> None:
            print(f"Hello, my name is {self.name} and I am {self.age} years old.")

    # Create instances (objects) of the class
    student1: Student = Student("Alice", 20)
    student2: Student = Student("Bob", 22)

    # Access instance variables and call methods
    print("Student 1:")
    student1.greet()
    print("Student 2:")
    student2.greet()


# Demonstrates how to define and use functions in Python
def demonstrate_functions() -> None:
    # Simple function with no arguments
    def greet() -> None:
        print("Hello from a function!")

    # Function with arguments
    def add(a: int, b: int) -> int:
        return a + b

    # Function with a default argument
    def say_hello(name: str = "World") -> None:
        print(f"Hello, {name}!")

    # Function with return value
    def square(x: int) -> int:
        return x * x

    # Calling the functions
    greet()
    result: int = add(3, 5)
    print("3 + 5 =", result)
    say_hello()
    say_hello("Alice")
    print("Square of 4:", square(4))


# Demonstrates control statements in Python
def demonstrate_control_statements() -> None:
    # if, elif, else
    x: int = 10
    if x > 10:
        print("x is greater than 10")
    elif x == 10:
        print("x is exactly 10")
    else:
        print("x is less than 10")

    # Using break and continue in a loop
    print("\nUsing break and continue:")
    for i in range(1, 6):
        if i == 3:
            print("Skipping 3")
            continue  # Skip the rest of the loop for i == 3
        if i == 5:
            print("Breaking at 5")
            break  # Exit the loop when i == 5
        print("i:", i)

    # pass statement (does nothing, placeholder)
    for j in range(2):
        pass  # This loop does nothing
        print(j, "This will not be printed because pass does nothing")


# Demonstrates loops over arrays (lists), tuples, and dictionaries
def demonstrate_loops() -> None:
    # Simple list
    numbers: list[int] = [1, 2, 3, 4, 5]
    print("Looping over a list:")
    for num in numbers:
        print(num)

    # List of dictionaries (object basis)
    students: list[dict[str, int | str]] = [
        {"name": "Alice", "age": 20},
        {"name": "Bob", "age": 22},
        {"name": "Charlie", "age": 21},
    ]
    print("\nLooping over a list of dictionaries:")
    for student in students:
        print("Name:", student["name"], "Age:", student["age"])

    # Tuple
    coordinates: tuple[int, ...] = (10, 20, 30)
    print("\nLooping over a tuple:")
    for coord in coordinates:
        print(coord, ":: cord")

    # Dictionary
    info: dict[str, str | int] = {"name": "Dana", "city": "NYC", "score": 95}
    print("\nLooping over a dictionary (keys and values):")
    for key, value in info.items():
        print(key, "::", value)

    print("\nLooping over dictionary keys:")
    for key in info:
        print(key)

    print("\nLooping over dictionary values:")
    for value in info.values():
        print(value)


# Demonstrates variable declarations of different types in Python
def demonstrate_variables() -> None:
    # Integer variable
    age: int = 25

    # Float variable
    height: float = 1.75

    # String variable
    name: str = "Alice"

    # Boolean variable
    is_student: bool = True

    # List variable
    scores: list[int] = [90, 85, 88]

    # Tuple variable
    position: tuple[int, int] = (10, 20)

    # Dictionary variable
    student_info: dict[str, int | str | float | bool] = {
        "name": name,
        "age": age,
        "height": height,
        "is_student": is_student,
    }

    # NoneType variable
    nothing: None = None

    # Print all variables
    print("Name:", name)
    print("Age:", age)
    print("Height:", height)
    print("Is student:", is_student)
    print("Scores:", scores, scores[0], scores[scores.__len__() - 1])
    print("Position:", position, position[0], position[position.__len__() - 1])
    print("Student info:", student_info, student_info["name"])
    print("Nothing:", nothing)


# learn_and_debug.py
# Use this file for learning and debugging Python code


def main() -> None:
    print("Welcome to your learn and debug script!")

    # demonstrate_variables()
    # demonstrate_loops()
    demonstrate_control_statements()
    # demonstrate_functions()
    demonstrate_oop_principles()
    # demonstrate_exception_handling()


if __name__ == "__main__":
    main()

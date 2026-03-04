function favorite(el, date, hash) {
  fetch("/favorites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      date: date,
      hash: hash,
      text: el.parentNode.children[0].innerText,
    }),
  });

  el.setAttribute(
    "data-favorite",
    el.attributes["data-favorite"].value === "True" ? "False" : "True",
  );

  return false;
}

function toggleTodo(checkbox) {
  const date = checkbox.dataset.date;
  const todoIndex = parseInt(checkbox.dataset.todoIndex, 10);
  const checked = checkbox.checked;
  const parts = date.split("-");
  const url = `/${parts[0]}/${parseInt(parts[1], 10)}/${parseInt(parts[2], 10)}`;

  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ todo_index: todoIndex, checked: checked }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Failed to update TODO");
      }

      const item = checkbox.closest(".todo-item");
      if (item) {
        if (checked) {
          item.classList.add("completed");
        } else {
          item.classList.remove("completed");
        }
      }
    })
    .catch(() => {
      checkbox.checked = !checked;
      alert("Failed to update TODO item");
    });
}
function favorite(el, date, hash) {
    fetch('/favorites', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({'date': date, 'hash': hash, 'text': el.parentNode.children[0].innerText})
    })

    el.setAttribute('data-favorite', el.attributes["data-favorite"].value === "True" ? "False" : "True");
}
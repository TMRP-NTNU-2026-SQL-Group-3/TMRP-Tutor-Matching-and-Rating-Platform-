import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useMatchStore = defineStore('match', () => {
  const matches = ref([])

  function setMatches(data) {
    matches.value = data
  }

  return { matches, setMatches }
})

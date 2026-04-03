import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useTutorStore = defineStore('tutor', () => {
  const searchResults = ref([])
  const searchFilters = ref({})

  function setResults(results) {
    searchResults.value = results
  }

  function setFilters(filters) {
    searchFilters.value = filters
  }

  return { searchResults, searchFilters, setResults, setFilters }
})
